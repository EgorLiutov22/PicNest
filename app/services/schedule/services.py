"""
Сервисы модуля расписания PicNest.

Три сущности:
- ScheduleTemplate — недельный график работы (7 строк на ресурс, конфиг);
- ScheduleException — выходной или особые часы на конкретную дату;
- ScheduleBlock — ручная блокировка интервала.

Блокировка пишется ещё и в resource_occupancy, поэтому конфликт с бронью
ловит exclusion constraint, а не проверка перед вставкой. Шаблоны в
занятость не разворачиваются: это конфиг, а не занятые слоты.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.photographerprofile import PhotographerProfile
from app.models.schedule import ScheduleBlock, ScheduleException, ScheduleTemplate
from app.models.studioprofile import StudioProfile
from app.models.studioroom import StudioRoom
from app.services.schedule.occupancy import SlotTakenError, occupy, release, _to_utc


# ============================================================================
# Исключения модуля
# ============================================================================

class ScheduleError(AppException):
    """Базовое исключение модуля расписания."""

    def __init__(self, detail: str, error_code: str, status_code: int):
        super().__init__(detail=detail, error_code=error_code)
        self.status_code = status_code


class ScheduleValidationError(ScheduleError):
    """Некорректные данные расписания."""

    def __init__(self, detail: str, error_code: str = "SCHEDULE_VALIDATION_ERROR"):
        super().__init__(detail, error_code, 400)


class ScheduleConflictError(ScheduleError):
    """Конфликт: пересечение интервалов или дубль записи."""

    def __init__(self, detail: str, error_code: str = "SCHEDULE_CONFLICT"):
        super().__init__(detail, error_code, 409)


class ScheduleAccessDeniedError(ScheduleError):
    """Чужое расписание."""

    def __init__(self, detail: str, error_code: str = "SCHEDULE_ACCESS_DENIED"):
        super().__init__(detail, error_code, 403)


class ScheduleNotFoundError(ScheduleError):
    """Запись расписания не найдена."""

    def __init__(self, detail: str, error_code: str = "SCHEDULE_NOT_FOUND"):
        super().__init__(detail, error_code, 404)


# pgcode unique_violation: так приходит нарушение частичного уникального
# индекса по (владелец, день недели).
UNIQUE_VIOLATION = "23505"


def _is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(getattr(exc, "orig", None), "pgcode", None) == UNIQUE_VIOLATION


# ============================================================================
# Владение ресурсом
# ============================================================================

OWNER_COLUMNS = {
    "photographer": "photographer_id",
    "room": "room_id",
}


async def ensure_owner_access(
    db: AsyncSession,
    owner_id: int,
    owner_type: str,
    user_id: Optional[str],
) -> None:
    """Проверяет, что профиль/зал существует и принадлежит пользователю.

    Проверка идёт по цепочке пользователь -> профиль студии -> зал:
    у User нет поля studio_profile_id, а привязка живёт в StudioProfile.
    """
    if owner_type == "photographer":
        result = await db.execute(
            select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
        )
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ScheduleNotFoundError(
                f"Фотограф с id={owner_id} не найден", "PHOTOGRAPHER_NOT_FOUND"
            )
        if user_id is not None and str(owner.user_id) != str(user_id):
            raise ScheduleAccessDeniedError(
                "Фотограф может управлять только своим расписанием", "OWN_PROFILE_ONLY"
            )
        return

    if owner_type == "room":
        result = await db.execute(
            select(StudioRoom).where(StudioRoom.id == owner_id)
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise ScheduleNotFoundError(f"Зал с id={owner_id} не найден", "ROOM_NOT_FOUND")

        if user_id is not None:
            result = await db.execute(
                select(StudioProfile).where(StudioProfile.id == room.studio_id)
            )
            studio = result.scalar_one_or_none()
            if studio is None or str(studio.user_id) != str(user_id):
                raise ScheduleAccessDeniedError(
                    "Представитель студии может управлять только своими залами",
                    "OWN_ROOMS_ONLY",
                )
        return

    raise ScheduleValidationError(
        f"Некорректный тип владельца: {owner_type}", "INVALID_OWNER_TYPE"
    )


def owner_fields(owner_id: int, owner_type: str) -> Dict[str, Any]:
    """Поля владельца для создания записи."""
    if owner_type not in OWNER_COLUMNS:
        raise ScheduleValidationError(
            f"Некорректный тип владельца: {owner_type}", "INVALID_OWNER_TYPE"
        )
    return {
        "photographer_id": owner_id if owner_type == "photographer" else None,
        "room_id": owner_id if owner_type == "room" else None,
    }


def _owner_of(row) -> Tuple[int, str]:
    """Обратное преобразование: возвращает (owner_id, owner_type)."""
    if row.photographer_id is not None:
        return row.photographer_id, "photographer"
    return row.room_id, "room"


# ============================================================================
# Шаблоны
# ============================================================================

class ScheduleTemplateService:

    @staticmethod
    async def create_template(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        day_of_week: int,
        start_time: time,
        end_time: time,
        user_id: Optional[str] = None,
    ) -> ScheduleTemplate:
        if end_time <= start_time:
            raise ScheduleValidationError(
                "Время окончания должно быть строго после времени начала",
                "INVALID_TIME_RANGE",
            )

        await ensure_owner_access(db, owner_id, owner_type, user_id)

        template = ScheduleTemplate(
            **owner_fields(owner_id, owner_type),
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
        )
        db.add(template)

        try:
            await db.flush()
        except IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
            raise ScheduleConflictError(
                f"Расписание на этот день уже задано (day_of_week={day_of_week})",
                "TEMPLATE_ALREADY_EXISTS",
            ) from exc

        return template

    @staticmethod
    async def get_template(
        db: AsyncSession, template_id: int, user_id: Optional[str] = None
    ) -> ScheduleTemplate:
        result = await db.execute(
            select(ScheduleTemplate).where(ScheduleTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise ScheduleNotFoundError(
                f"Шаблон с id={template_id} не найден", "TEMPLATE_NOT_FOUND"
            )

        owner_id, owner_type = _owner_of(template)
        await ensure_owner_access(db, owner_id, owner_type, user_id)
        return template

    @staticmethod
    async def get_templates_by_owner(
        db: AsyncSession,
        owner_id: Optional[int],
        owner_type: str,
        user_id: Optional[str] = None,
        day_of_week: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ScheduleTemplate], int]:
        if owner_id is not None:
            await ensure_owner_access(db, owner_id, owner_type, user_id)
            conditions = [getattr(ScheduleTemplate, OWNER_COLUMNS[owner_type]) == owner_id]
        else:
            # Без owner_id показываем только своё: иначе пользователь
            # увидел бы чужой график перебором id.
            conditions = [await _own_condition(db, ScheduleTemplate, owner_type, user_id)]

        if day_of_week is not None:
            conditions.append(ScheduleTemplate.day_of_week == day_of_week)

        where = and_(*conditions)

        total = (
            await db.execute(select(func.count(ScheduleTemplate.id)).where(where))
        ).scalar() or 0

        result = await db.execute(
            select(ScheduleTemplate)
            .where(where)
            .order_by(ScheduleTemplate.day_of_week)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def update_template(
        db: AsyncSession,
        template_id: int,
        updates: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> ScheduleTemplate:
        template = await ScheduleTemplateService.get_template(db, template_id, user_id)

        for field in ("day_of_week", "start_time", "end_time"):
            if field in updates and updates[field] is not None:
                setattr(template, field, updates[field])

        if template.end_time <= template.start_time:
            raise ScheduleValidationError(
                "Время окончания должно быть строго после времени начала",
                "INVALID_TIME_RANGE",
            )

        try:
            await db.flush()
        except IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
            raise ScheduleConflictError(
                "Расписание на этот день уже задано", "TEMPLATE_ALREADY_EXISTS"
            ) from exc

        return template

    @staticmethod
    async def delete_template(
        db: AsyncSession, template_id: int, user_id: Optional[str] = None
    ) -> None:
        template = await ScheduleTemplateService.get_template(db, template_id, user_id)
        await db.delete(template)
        await db.flush()


async def _own_condition(db: AsyncSession, model, owner_type: str, user_id: Optional[str]):
    """Условие «записи принадлежат этому пользователю»."""
    if user_id is None:
        # Без пользователя отдавать нечего; заведомо ложное условие
        # дешевле отдельной ветки с пустым результатом.
        return model.id.is_(None)

    if owner_type == "photographer":
        profile_ids = select(PhotographerProfile.id).where(
            PhotographerProfile.user_id == user_id
        )
        return model.photographer_id.in_(profile_ids)

    room_ids = select(StudioRoom.id).where(
        StudioRoom.studio_id.in_(
            select(StudioProfile.id).where(StudioProfile.user_id == user_id)
        )
    )
    return model.room_id.in_(room_ids)


# ============================================================================
# Исключения из расписания
# ============================================================================

class ScheduleExceptionService:

    @staticmethod
    async def create_exception(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        exception_date: date,
        is_day_off: bool = False,
        custom_start_time: Optional[time] = None,
        custom_end_time: Optional[time] = None,
        user_id: Optional[str] = None,
    ) -> ScheduleException:
        if not is_day_off:
            if custom_start_time is None or custom_end_time is None:
                raise ScheduleValidationError(
                    "При is_day_off=False нужно указать время работы",
                    "MISSING_WORKING_HOURS",
                )
            if custom_end_time <= custom_start_time:
                raise ScheduleValidationError(
                    "Время окончания должно быть позже времени начала",
                    "INVALID_TIME_RANGE",
                )

        await ensure_owner_access(db, owner_id, owner_type, user_id)

        exception = ScheduleException(
            **owner_fields(owner_id, owner_type),
            date=exception_date,
            is_day_off=is_day_off,
            # При выходном дне часы не храним: иначе после смены
            # is_day_off на False остались бы устаревшие значения.
            custom_start_time=None if is_day_off else custom_start_time,
            custom_end_time=None if is_day_off else custom_end_time,
        )
        db.add(exception)
        await db.flush()
        return exception

    @staticmethod
    async def get_exception(
        db: AsyncSession, exception_id: int, user_id: Optional[str] = None
    ) -> ScheduleException:
        result = await db.execute(
            select(ScheduleException).where(ScheduleException.id == exception_id)
        )
        exception = result.scalar_one_or_none()
        if exception is None:
            raise ScheduleNotFoundError(
                f"Исключение с id={exception_id} не найдено", "EXCEPTION_NOT_FOUND"
            )

        owner_id, owner_type = _owner_of(exception)
        await ensure_owner_access(db, owner_id, owner_type, user_id)
        return exception

    @staticmethod
    async def get_exceptions_by_owner(
        db: AsyncSession,
        owner_id: Optional[int],
        owner_type: str,
        user_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ScheduleException], int]:
        if owner_id is not None:
            await ensure_owner_access(db, owner_id, owner_type, user_id)
            conditions = [getattr(ScheduleException, OWNER_COLUMNS[owner_type]) == owner_id]
        else:
            conditions = [await _own_condition(db, ScheduleException, owner_type, user_id)]

        if date_from is not None:
            conditions.append(ScheduleException.date >= date_from)
        if date_to is not None:
            conditions.append(ScheduleException.date <= date_to)

        where = and_(*conditions)

        total = (
            await db.execute(select(func.count(ScheduleException.id)).where(where))
        ).scalar() or 0

        result = await db.execute(
            select(ScheduleException)
            .where(where)
            .order_by(ScheduleException.date)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def update_exception(
        db: AsyncSession,
        exception_id: int,
        updates: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> ScheduleException:
        exception = await ScheduleExceptionService.get_exception(
            db, exception_id, user_id
        )

        for field in ("is_day_off", "custom_start_time", "custom_end_time"):
            if field in updates:
                setattr(exception, field, updates[field])

        if exception.is_day_off:
            exception.custom_start_time = None
            exception.custom_end_time = None
        else:
            if exception.custom_start_time is None or exception.custom_end_time is None:
                raise ScheduleValidationError(
                    "При is_day_off=False нужно указать время работы",
                    "MISSING_WORKING_HOURS",
                )
            if exception.custom_end_time <= exception.custom_start_time:
                raise ScheduleValidationError(
                    "Время окончания должно быть позже времени начала",
                    "INVALID_TIME_RANGE",
                )

        await db.flush()
        return exception

    @staticmethod
    async def delete_exception(
        db: AsyncSession, exception_id: int, user_id: Optional[str] = None
    ) -> None:
        exception = await ScheduleExceptionService.get_exception(
            db, exception_id, user_id
        )
        await db.delete(exception)
        await db.flush()


# ============================================================================
# Блокировки
# ============================================================================

class ScheduleBlockService:

    @staticmethod
    async def create_block(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        start_at: datetime,
        end_at: datetime,
        reason: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ScheduleBlock:
        """Создаёт блокировку и занимает интервал в resource_occupancy.

        Пересечение с бронью или другой блокировкой ловит constraint, а не
        SELECT перед вставкой: иначе между проверкой и записью влезает
        параллельный заказ.
        """
        start_at = _to_utc(start_at)
        end_at = _to_utc(end_at)

        if end_at <= start_at:
            raise ScheduleValidationError(
                "Конец блокировки должен быть позже начала", "INVALID_TIME_RANGE"
            )

        await ensure_owner_access(db, owner_id, owner_type, user_id)

        block = ScheduleBlock(
            **owner_fields(owner_id, owner_type),
            start_at=start_at,
            end_at=end_at,
            reason=reason,
        )
        db.add(block)
        await db.flush()

        # resource_type зала — "studio_room": то же значение, что пишет
        # создание заказа, иначе бронь и блокировка не увидели бы друг друга.
        resource_type = "photographer" if owner_type == "photographer" else "studio_room"

        try:
            # savepoint обязателен: нарушение constraint в PostgreSQL
            # прерывает всю транзакцию, и следующий SELECT (даже чтобы
            # прочитать конфликт) падает с PendingRollbackError.
            async with db.begin_nested():
                await occupy(
                    db,
                    resource_type=resource_type,
                    resource_id=owner_id,
                    start_time=start_at,
                    end_time=end_at,
                    kind="block",
                    block_id=block.id,
                    expires_at=None,
                )
        except SlotTakenError as exc:
            from app.services.schedule.occupancy import find_conflict

            conflict = await find_conflict(
                db,
                resource_type=resource_type,
                resource_id=owner_id,
                start_time=start_at,
                end_time=end_at,
            )
            raise ScheduleConflictError(
                f"Интервал пересекается с существующей занятостью: {conflict}",
                "BLOCK_OVERLAPS_BOOKING",
            ) from exc

        return block

    @staticmethod
    async def get_block(
        db: AsyncSession, block_id: int, user_id: Optional[str] = None
    ) -> ScheduleBlock:
        result = await db.execute(
            select(ScheduleBlock).where(ScheduleBlock.id == block_id)
        )
        block = result.scalar_one_or_none()
        if block is None:
            raise ScheduleNotFoundError(
                f"Блокировка с id={block_id} не найдена", "BLOCK_NOT_FOUND"
            )

        owner_id, owner_type = _owner_of(block)
        await ensure_owner_access(db, owner_id, owner_type, user_id)
        return block

    @staticmethod
    async def get_blocks_by_owner(
        db: AsyncSession,
        owner_id: Optional[int],
        owner_type: str,
        user_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[ScheduleBlock], int]:
        if owner_id is not None:
            await ensure_owner_access(db, owner_id, owner_type, user_id)
            conditions = [getattr(ScheduleBlock, OWNER_COLUMNS[owner_type]) == owner_id]
        else:
            conditions = [await _own_condition(db, ScheduleBlock, owner_type, user_id)]

        # Фильтр по датам клиент задаёт в календарных днях, поэтому
        # сравниваем с границами суток, а не с точным временем.
        if date_from is not None:
            conditions.append(
                ScheduleBlock.end_at >= datetime.combine(
                    date_from, time.min, tzinfo=timezone.utc
                )
            )
        if date_to is not None:
            conditions.append(
                ScheduleBlock.start_at <= datetime.combine(
                    date_to, time.max, tzinfo=timezone.utc
                )
            )

        where = and_(*conditions)

        total = (
            await db.execute(select(func.count(ScheduleBlock.id)).where(where))
        ).scalar() or 0

        result = await db.execute(
            select(ScheduleBlock)
            .where(where)
            .order_by(ScheduleBlock.start_at)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def delete_block(
        db: AsyncSession, block_id: int, user_id: Optional[str] = None
    ) -> None:
        """Снимает блокировку вместе с занятостью интервала."""
        block = await ScheduleBlockService.get_block(db, block_id, user_id)
        await release(db, kind="block", block_id=block.id)
        await db.delete(block)
        await db.flush()
