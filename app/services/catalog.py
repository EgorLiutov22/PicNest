"""
Каталог: студии, залы, фотографы и расчёт доступности.

Доступность считается из трёх источников:
- resource_occupancy — реальная занятость (брони + блокировки);
- schedule_templates — плановые часы по дням недели;
- schedule_exceptions — выходные и изменённые часы на дату.

Шаблоны намеренно не разворачиваются в строки занятости: на 200 залов
× 365 дней это десятки тысяч записей в год ни за что.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.photographerprofile import PhotographerProfile
from app.models.photographerservice import PhotographerService
from app.models.schedule import ScheduleException, ScheduleTemplate
from app.models.studioprofile import StudioProfile
from app.models.studioroom import StudioRoom
from app.services.schedule.occupancy import find_occupied

# Защита от запроса на несколько лет вперёд: каждая дата — отдельная
# итерация по шаблону.
MAX_AVAILABILITY_DAYS = 62

OWNER_TYPE_BY_RESOURCE = {
    "photographer": "photographer",
    "studio_room": "room",
}


def _tz(name: Optional[str]):
    try:
        return ZoneInfo(name or "Europe/Moscow")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Moscow")


class CatalogService:

    @staticmethod
    async def list_studios(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        """Студии со счётчиком залов и минимальной ценой.

        Агрегаты считаются подзапросом, а не отдельными запросами на
        каждую студию: иначе на двадцати студиях получается N+1.
        """
        conditions = []
        if search:
            conditions.append(StudioProfile.title.ilike(f"%{search}%"))

        total = (
            await db.execute(
                select(func.count(StudioProfile.id)).where(*conditions)
            )
        ).scalar() or 0

        rooms_agg = (
            select(
                StudioRoom.studio_id.label("studio_id"),
                func.count(StudioRoom.id).label("rooms_count"),
                func.min(StudioRoom.price_per_hour).label("min_price"),
            )
            .group_by(StudioRoom.studio_id)
            .subquery()
        )

        result = await db.execute(
            select(
                StudioProfile,
                func.coalesce(rooms_agg.c.rooms_count, 0),
                rooms_agg.c.min_price,
            )
            .outerjoin(rooms_agg, rooms_agg.c.studio_id == StudioProfile.id)
            .where(*conditions)
            .order_by(StudioProfile.rating.desc(), StudioProfile.id)
            .offset(skip)
            .limit(limit)
        )

        items = [
            {
                "id": studio.id,
                "title": studio.title,
                "address": studio.address,
                "rating": studio.rating,
                "rooms_count": rooms_count,
                "min_price_per_hour": min_price,
            }
            for studio, rooms_count, min_price in result.all()
        ]
        return items, total

    @staticmethod
    async def get_studio(db: AsyncSession, studio_id: int) -> dict:
        result = await db.execute(
            select(StudioProfile).where(StudioProfile.id == studio_id)
        )
        studio = result.scalar_one_or_none()
        if studio is None:
            raise NotFoundException(
                resource_type="studio",
                detail=f"Студия с id={studio_id} не найдена",
                error_code="STUDIO_NOT_FOUND",
            )

        result = await db.execute(
            select(StudioRoom)
            .where(StudioRoom.studio_id == studio_id)
            .order_by(StudioRoom.price_per_hour)
        )
        rooms = list(result.scalars().all())

        return {
            "id": studio.id,
            "title": studio.title,
            "description": studio.description,
            "address": studio.address,
            "rating": studio.rating,
            "rooms_count": len(rooms),
            "min_price_per_hour": min(
                (r.price_per_hour for r in rooms), default=None
            ),
            "rooms": rooms,
        }

    @staticmethod
    async def list_photographers(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        conditions = []
        if search:
            conditions.append(PhotographerProfile.display_name.ilike(f"%{search}%"))

        total = (
            await db.execute(
                select(func.count(PhotographerProfile.id)).where(*conditions)
            )
        ).scalar() or 0

        services_agg = (
            select(
                PhotographerService.photographer_id.label("photographer_id"),
                func.count(PhotographerService.id).label("services_count"),
                func.min(PhotographerService.price).label("min_price"),
            )
            .group_by(PhotographerService.photographer_id)
            .subquery()
        )

        result = await db.execute(
            select(
                PhotographerProfile,
                func.coalesce(services_agg.c.services_count, 0),
                services_agg.c.min_price,
            )
            .outerjoin(
                services_agg,
                services_agg.c.photographer_id == PhotographerProfile.id,
            )
            .where(*conditions)
            .order_by(PhotographerProfile.rating.desc(), PhotographerProfile.id)
            .offset(skip)
            .limit(limit)
        )

        items = [
            {
                "id": profile.id,
                "display_name": profile.display_name,
                "avatar_url": profile.avatar_url,
                "rating": profile.rating,
                "services_count": services_count,
                "min_price": min_price,
            }
            for profile, services_count, min_price in result.all()
        ]
        return items, total

    @staticmethod
    async def get_photographer(db: AsyncSession, photographer_id: int) -> dict:
        result = await db.execute(
            select(PhotographerProfile).where(PhotographerProfile.id == photographer_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise NotFoundException(
                resource_type="photographer",
                detail=f"Фотограф с id={photographer_id} не найден",
                error_code="PHOTOGRAPHER_NOT_FOUND",
            )

        result = await db.execute(
            select(PhotographerService)
            .where(PhotographerService.photographer_id == photographer_id)
            .order_by(PhotographerService.price)
        )
        services = list(result.scalars().all())

        return {
            "id": profile.id,
            "display_name": profile.display_name,
            "bio": profile.bio,
            "avatar_url": profile.avatar_url,
            "legal_status": profile.legal_status,
            "rating": profile.rating,
            "services_count": len(services),
            "min_price": min((s.price for s in services), default=None),
            "services": services,
        }

    @staticmethod
    async def get_availability(
        db: AsyncSession,
        resource_type: str,
        resource_id: int,
        date_from: date,
        date_to: date,
        user_timezone: Optional[str] = None,
    ) -> dict:
        """Занятость и свободные окна ресурса.

        Рабочие часы берутся по часовому поясу пользователя: шаблон хранит
        локальное время («с 9 до 18»), а период в БД — UTC.
        """
        if resource_type not in OWNER_TYPE_BY_RESOURCE:
            raise NotFoundException(
                resource_type="resource",
                detail=f"Неизвестный тип ресурса: {resource_type}",
                error_code="UNKNOWN_RESOURCE_TYPE",
            )

        await _ensure_resource_exists(db, resource_type, resource_id)

        if date_to < date_from:
            date_from, date_to = date_to, date_from

        if (date_to - date_from).days > MAX_AVAILABILITY_DAYS:
            date_to = date_from + timedelta(days=MAX_AVAILABILITY_DAYS)

        tz = _tz(user_timezone)

        window_start = datetime.combine(date_from, time.min, tzinfo=tz)
        window_end = datetime.combine(date_to, time.max, tzinfo=tz)

        busy = await find_occupied(
            db,
            resource_type=resource_type,
            resource_id=resource_id,
            start_time=window_start,
            end_time=window_end,
        )

        free = await _free_slots(
            db,
            resource_type=resource_type,
            resource_id=resource_id,
            date_from=date_from,
            date_to=date_to,
            tz=tz,
            busy=busy,
        )

        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timezone": str(tz),
            "date_from": date_from,
            "date_to": date_to,
            "busy": busy,
            "free": free,
        }


async def _ensure_resource_exists(
    db: AsyncSession, resource_type: str, resource_id: int
) -> None:
    model = StudioRoom if resource_type == "studio_room" else PhotographerProfile
    if not await _row_exists(db, model, resource_id):
        raise NotFoundException(
            resource_type=resource_type,
            detail=f"Ресурс {resource_type} с id={resource_id} не найден",
            error_code="RESOURCE_NOT_FOUND",
        )


async def _row_exists(db: AsyncSession, model, resource_id: int) -> bool:
    result = await db.execute(select(model.id).where(model.id == resource_id))
    return result.scalar_one_or_none() is not None


async def _free_slots(
    db: AsyncSession,
    *,
    resource_type: str,
    resource_id: int,
    date_from: date,
    date_to: date,
    tz,
    busy: List[dict],
) -> List[dict]:
    """Рабочие окна по шаблону минус занятые интервалы.

    Один запрос на шаблоны и один на исключения — не на каждую дату.
    """
    owner_column = (
        ScheduleTemplate.photographer_id
        if OWNER_TYPE_BY_RESOURCE[resource_type] == "photographer"
        else ScheduleTemplate.room_id
    )
    templates = (
        await db.execute(select(ScheduleTemplate).where(owner_column == resource_id))
    ).scalars().all()

    by_day = {t.day_of_week: t for t in templates}

    exception_model_column = (
        ScheduleException.photographer_id
        if OWNER_TYPE_BY_RESOURCE[resource_type] == "photographer"
        else ScheduleException.room_id
    )
    exceptions = (
        await db.execute(
            select(ScheduleException).where(
                and_(
                    exception_model_column == resource_id,
                    ScheduleException.date >= date_from,
                    ScheduleException.date <= date_to,
                )
            )
        )
    ).scalars().all()
    exceptions_by_date = {e.date: e for e in exceptions}

    windows: List[Tuple[datetime, datetime]] = []
    current = date_from
    while current <= date_to:
        exception = exceptions_by_date.get(current)

        if exception is not None and exception.is_day_off:
            current += timedelta(days=1)
            continue

        if exception is not None and exception.custom_start_time:
            start_t, end_t = exception.custom_start_time, exception.custom_end_time
        else:
            template = by_day.get(current.isoweekday())
            if template is None:
                current += timedelta(days=1)
                continue
            start_t, end_t = template.start_time, template.end_time

        start_dt = datetime.combine(current, start_t, tzinfo=tz)
        end_dt = datetime.combine(current, end_t, tzinfo=tz)
        if end_dt > start_dt:
            windows.append((start_dt, end_dt))

        current += timedelta(days=1)

    return _subtract_busy(windows, busy)


def _subtract_busy(
    windows: List[Tuple[datetime, datetime]], busy: List[dict]
) -> List[dict]:
    """Вычитает занятые интервалы из рабочих окон.

    Пересечения не предполагаются (constraint), но вычитание идёт по
    каждому окну отдельно, поэтому лишняя запись просто дополнительно
    урежет окно, а не сломает результат.
    """
    busy_sorted = sorted(busy, key=lambda b: b["start"])
    result: List[dict] = []

    for window_start, window_end in windows:
        cursor = window_start

        for interval in busy_sorted:
            busy_start = interval["start"]
            busy_end = interval["end"]

            if busy_end <= cursor or busy_start >= window_end:
                continue

            if busy_start > cursor:
                result.append({"start": cursor, "end": min(busy_start, window_end)})

            cursor = max(cursor, busy_end)
            if cursor >= window_end:
                break

        if cursor < window_end:
            result.append({"start": cursor, "end": window_end})

    return result
