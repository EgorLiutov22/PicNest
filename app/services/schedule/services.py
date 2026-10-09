"""
Сервисы для модуля управления расписанием PicNest.

Этот модуль содержит бизнес-логику и сервисные функции для работы с:
- Недельными шаблонами расписания (ScheduleTemplate)
- Исключениями из расписания (ScheduleException)
- Блокировками временных слотов (ScheduleBlock)

Сервисы обеспечивают:
- Валидацию данных на уровне приложения
- Проверку пересечений при создании блокировок
- RBAC проверки для фотографов и представителей студий
- Транзакционную целостность операций с базой данных
"""

from datetime import date, time, datetime
from typing import List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError


# ============================================================================
# Custom exceptions for schedule module
# ============================================================================

class ScheduleValidationError(AppError):
    """Ошибка валидации данных расписания."""
    status_code = 400


class ScheduleConflictError(AppError):
    """Конфликт при создании/обновлении расписания (пересечения)."""
    status_code = 409


class ScheduleAccessDeniedError(AppError):
    """Отказ в доступе к управлению чужим расписанием."""
    status_code = 403


class ScheduleNotFoundError(AppError):
    """Запись расписания не найдена."""
    status_code = 404


# ============================================================================
# Helper functions for time validation and comparison
# ============================================================================

def validate_time_range(start: time, end: time) -> bool:
    """Проверяет, что время начала строго меньше времени окончания.
    
    Args:
        start: Время начала
        end: Время окончания
        
    Returns:
        True если диапазон валиден
        
    Raises:
        ScheduleValidationError: Если время некорректно
    """
    if start >= end:
        raise ScheduleValidationError(
            status_code=400,
            detail="Время начала работы должно быть строго меньше времени окончания"
        )
    return True


def validate_date_range(start: date, end: date) -> bool:
    """Проверяет, что дата начала строго меньше даты окончания.
    
    Args:
        start: Дата начала
        end: Дата окончания
        
    Returns:
        True если диапазон валиден
        
    Raises:
        ScheduleValidationError: Если дата некорректна
    """
    if start >= end:
        raise ScheduleValidationError(
            status_code=400,
            detail="Дата начала должна быть строго меньше даты окончания"
        )
    return True


# ============================================================================
# Schedule Template Service
# ============================================================================

class ScheduleTemplateService:
    """Сервис для управления недельными шаблонами расписания."""

    @staticmethod
    async def create_template(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        day_of_week: int,
        start_time: time,
        end_time: time,
        user_id: Optional[str] = None
    ) -> Any:
        """Создаёт новый шаблон расписания.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца (photographer_profile.id или room.id)
            owner_type: Тип владельца ('photographer' или 'room')
            day_of_week: День недели (1-7)
            start_time: Время начала работы
            end_time: Время окончания работы
            user_id: ID текущего пользователя для проверки прав доступа
            
        Returns:
            Созданная запись шаблона расписания
            
        Raises:
            ScheduleValidationError: Если время некорректно или день недели вне диапазона
            ScheduleAccessDeniedError: Если пользователь не имеет прав на создание
            ScheduleNotFoundError: Если владелец не найден
        """
        # Валидация времени
        validate_time_range(start_time, end_time)
        
        if not 1 <= day_of_week <= 7:
            raise ScheduleValidationError(
                status_code=400,
                detail="День недели должен быть в диапазоне от 1 до 7"
            )

        # Загрузка модели для проверки существования владельца
        from app.models.sheduletemplate import ScheduleTemplate
        
        if owner_type == 'photographer':
            from app.models.photographerprofile import PhotographerProfile
            result = await db.execute(
                select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
            )
            owner = result.scalar_one_or_none()
            
            # Проверка прав доступа для фотографов
            if user_id and owner:
                if str(owner.user_id) != user_id:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Фотограф может редактировать только своё расписание"
                    )
        elif owner_type == 'room':
            from app.models.studioroom import StudioRoom
            result = await db.execute(
                select(StudioRoom).where(StudioRoom.id == owner_id)
            )
            room = result.scalar_one_or_none()
            
            # Проверка прав доступа для представителей студий
            if user_id and room:
                from app.models.studioprofile import StudioProfile
                studio_result = await db.execute(
                    select(StudioProfile).where(StudioProfile.id == room.studio_id)
                )
                studio = studio_result.scalar_one_or_none()
                
                # Проверяем, что пользователь является представителем студии
                from app.models.user import User
                user_result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                current_user = user_result.scalar_one_or_none()
                
                if current_user and (current_user.role != 'studio' or 
                                     str(current_user.studio_profile_id) != str(room.studio_id)):
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Представитель студии может управлять расписанием только своих залов"
                    )
        else:
            raise ScheduleValidationError(
                status_code=400,
                detail="Некорректный тип владельца"
            )

        if not owner and not room:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Владелец (owner_id={owner_id}, type={owner_type}) не найден"
            )

        # Создание записи шаблона
        template = ScheduleTemplate(
            photographer_id=owner_id if owner_type == 'photographer' else None,
            room_id=owner_id if owner_type == 'room' else None,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
        )
        
        db.add(template)
        await db.commit()
        await db.refresh(template)

        return template

    @staticmethod
    async def get_template(
        db: AsyncSession, 
        template_id: int,
        user_id: Optional[str] = None
    ) -> Any:
        """Получает шаблон расписания по ID.
        
        Args:
            db: Асинхронная сессия базы данных
            template_id: ID шаблона
            user_id: ID текущего пользователя
            
        Returns:
            Запись шаблона или None если не найдена/нет прав
            
        Raises:
            ScheduleNotFoundError: Если шаблон не найден и пользователь администратор
        """
        from app.models.sheduletemplate import ScheduleTemplate
        
        result = await db.execute(
            select(ScheduleTemplate).where(ScheduleTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Шаблон расписания с ID {template_id} не найден"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                # Обычный пользователь может видеть только своё расписание
                is_owner = False
                
                if template.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == template.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif template.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == template.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на просмотр этого шаблона расписания"
                    )

        return template

    @staticmethod
    async def get_templates_by_owner(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        user_id: Optional[str] = None,
        day_of_week: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Any], int]:
        """Получает список шаблонов расписания для владельца.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца
            owner_type: Тип владельца
            user_id: ID текущего пользователя
            day_of_week: Фильтр по дню недели (опционально)
            skip: Количество записей для пропуска
            limit: Максимальное количество записей
            
        Returns:
            Кортеж из списка шаблонов и общего количества
        """
        from app.models.sheduletemplate import ScheduleTemplate
        
        query = select(ScheduleTemplate).where(
            or_(
                and_(ScheduleTemplate.photographer_id == owner_id, ScheduleTemplate.room_id.is_(None)),
                and_(ScheduleTemplate.room_id == owner_id, ScheduleTemplate.photographer_id.is_(None))
            )
        )
        
        if day_of_week is not None:
            query = query.where(ScheduleTemplate.day_of_week == day_of_week)

        # Проверка прав доступа
        if user_id:
            from app.models.user import User
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_accessible = False
                
                if owner_type == 'photographer':
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    is_accessible = (photographer and str(photographer.user_id) == user_id)
                    
                elif owner_type == 'room':
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == owner_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        is_accessible = (studio and str(studio.user_id) == user_id)

                if not is_accessible:
                    return [], 0
        
        # Получение общего количества
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        templates = result.scalars().all()

        return list(templates), total

    @staticmethod
    async def update_template(
        db: AsyncSession,
        template_id: int,
        updates: dict,
        user_id: Optional[str] = None
    ) -> Any:
        """Обновляет существующий шаблон расписания.
        
        Args:
            db: Асинхронная сессия базы данных
            template_id: ID шаблона для обновления
            updates: Словарь с полями для обновления
            user_id: ID текущего пользователя
            
        Returns:
            Обновленная запись шаблона
            
        Raises:
            ScheduleNotFoundError: Если шаблон не найден
            ScheduleAccessDeniedError: Если нет прав на обновление
            ScheduleValidationError: Если данные некорректны
        """
        from app.models.sheduletemplate import ScheduleTemplate
        
        # Получение существующего шаблона
        result = await db.execute(
            select(ScheduleTemplate).where(ScheduleTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Шаблон расписания с ID {template_id} не найден"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if template.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == template.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif template.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == template.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на обновление этого шаблона расписания"
                    )

        # Валидация обновляемых полей
        if 'start_time' in updates and 'end_time' in updates:
            validate_time_range(updates['start_time'], updates['end_time'])
        elif 'start_time' in updates or 'end_time' in updates:
            raise ScheduleValidationError(
                status_code=400,
                detail="Необходимо обновлять start_time и end_time одновременно"
            )

        if 'day_of_week' in updates and not 1 <= updates['day_of_week'] <= 7:
            raise ScheduleValidationError(
                status_code=400,
                detail="День недели должен быть в диапазоне от 1 до 7"
            )

        # Применение обновлений
        for field, value in updates.items():
            if hasattr(template, field):
                setattr(template, field, value)

        await db.commit()
        await db.refresh(template)

        return template

    @staticmethod
    async def delete_template(
        db: AsyncSession, 
        template_id: int, 
        user_id: Optional[str] = None
    ) -> bool:
        """Удаляет шаблон расписания.
        
        Args:
            db: Асинхронная сессия базы данных
            template_id: ID шаблона для удаления
            user_id: ID текущего пользователя
            
        Returns:
            True если успешно удален
            
        Raises:
            ScheduleNotFoundError: Если шаблон не найден
            ScheduleAccessDeniedError: Если нет прав на удаление
        """
        from app.models.sheduletemplate import ScheduleTemplate
        
        result = await db.execute(
            select(ScheduleTemplate).where(ScheduleTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Шаблон расписания с ID {template_id} не найден"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if template.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == template.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif template.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == template.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на удаление этого шаблона расписания"
                    )

        await db.delete(template)
        await db.commit()

        return True


# ============================================================================
# Schedule Exception Service
# ============================================================================

class ScheduleExceptionService:
    """Сервис для управления исключениями из расписания."""

    @staticmethod
    async def create_exception(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        date_: date,
        is_day_off: bool = False,
        custom_start_time: Optional[time] = None,
        custom_end_time: Optional[time] = None,
        user_id: Optional[str] = None
    ) -> Any:
        """Создаёт исключение из расписания для конкретной даты.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца
            owner_type: Тип владельца
            date_: Дата исключения
            is_day_off: Является ли день выходным
            custom_start_time: Кастомное время начала (если not day off)
            custom_end_time: Кастомное время окончания (если not day off)
            user_id: ID текущего пользователя
            
        Returns:
            Созданная запись исключения
            
        Raises:
            ScheduleValidationError: Если данные некорректны
            ScheduleAccessDeniedError: Если нет прав на создание
            ScheduleNotFoundError: Если владелец не найден
        """
        # Валидация логики дня выходного/рабочего
        if is_day_off:
            if custom_start_time or custom_end_time:
                raise ScheduleValidationError(
                    status_code=400,
                    detail="Для дня выходного (is_day_off=True) нельзя указывать кастомное время"
                )
        else:
            if not custom_start_time or not custom_end_time:
                raise ScheduleValidationError(
                    status_code=400,
                    detail="При is_day_off=False необходимо указать custom_start_time и custom_end_time"
                )
            
            validate_time_range(custom_start_time, custom_end_time)

        # Проверка существования владельца
        if owner_type == 'photographer':
            from app.models.photographerprofile import PhotographerProfile
            result = await db.execute(
                select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
            )
            owner = result.scalar_one_or_none()
            
            # Проверка прав доступа
            if user_id and owner:
                if str(owner.user_id) != user_id:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Фотограф может редактировать только своё расписание"
                    )
        elif owner_type == 'room':
            from app.models.studioroom import StudioRoom
            result = await db.execute(
                select(StudioRoom).where(StudioRoom.id == owner_id)
            )
            room = result.scalar_one_or_none()
            
            # Проверка прав доступа
            if user_id and room:
                from app.models.studioprofile import StudioProfile
                studio_result = await db.execute(
                    select(StudioProfile).where(StudioProfile.id == room.studio_id)
                )
                studio = studio_result.scalar_one_or_none()
                
                from app.models.user import User
                user_result = await db.execute(select(User).where(User.id == user_id))
                current_user = user_result.scalar_one_or_none()
                
                if current_user and (current_user.role != 'studio' or 
                                     str(current_user.studio_profile_id) != str(room.studio_id)):
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Представитель студии может управлять расписанием только своих залов"
                    )
        else:
            raise ScheduleValidationError(
                status_code=400,
                detail="Некорректный тип владельца"
            )

        if not owner and not room:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Владелец (owner_id={owner_id}, type={owner_type}) не найден"
            )

        # Проверка на дубликаты (одна запись на одну дату для одного владельца)
        from app.models.shesuleexception import ScheduleException
        
        duplicate_query = select(ScheduleException).where(
            or_(
                and_(ScheduleException.photographer_id == owner_id, 
                     ScheduleException.room_id.is_(None)),
                and_(ScheduleException.room_id == owner_id, 
                     ScheduleException.photographer_id.is_(None))
            ),
            ScheduleException.date == date_
        )
        
        duplicate_result = await db.execute(duplicate_query)
        if duplicate_result.scalar_one_or_none():
            raise ScheduleConflictError(
                status_code=409,
                detail=f"Для владельца {owner_type} с ID {owner_id} уже существует исключение на дату {date_}"
            )

        # Создание записи исключения
        exception = ScheduleException(
            photographer_id=owner_id if owner_type == 'photographer' else None,
            room_id=owner_id if owner_type == 'room' else None,
            date=date_,
            is_day_off=is_day_off,
            custom_start_time=custom_start_time,
            custom_end_time=custom_end_time,
        )
        
        db.add(exception)
        await db.commit()
        await db.refresh(exception)

        return exception

    @staticmethod
    async def get_exception(
        db: AsyncSession, 
        exception_id: int,
        user_id: Optional[str] = None
    ) -> Any:
        """Получает исключение из расписания по ID.
        
        Args:
            db: Асинхронная сессия базы данных
            exception_id: ID исключения
            user_id: ID текущего пользователя
            
        Returns:
            Запись исключения или None если не найдена/нет прав
        """
        from app.models.shesuleexception import ScheduleException
        
        result = await db.execute(
            select(ScheduleException).where(ScheduleException.id == exception_id)
        )
        exception = result.scalar_one_or_none()

        if not exception:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Исключение из расписания с ID {exception_id} не найдено"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if exception.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == exception.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif exception.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == exception.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на просмотр этого исключения"
                    )

        return exception

    @staticmethod
    async def get_exceptions_by_owner(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        user_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Any], int]:
        """Получает список исключений из расписания для владельца.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца
            owner_type: Тип владельца
            user_id: ID текущего пользователя
            date_from: Фильтр по дате начала
            date_to: Фильтр по дате окончания
            skip: Количество записей для пропуска
            limit: Максимальное количество записей
            
        Returns:
            Кортеж из списка исключений и общего количества
        """
        from app.models.shesuleexception import ScheduleException
        
        query = select(ScheduleException).where(
            or_(
                and_(ScheduleException.photographer_id == owner_id, ScheduleException.room_id.is_(None)),
                and_(ScheduleException.room_id == owner_id, ScheduleException.photographer_id.is_(None))
            )
        )

        if date_from:
            query = query.where(ScheduleException.date >= date_from)
        
        if date_to:
            query = query.where(ScheduleException.date <= date_to)

        # Проверка прав доступа
        if user_id:
            from app.models.user import User
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_accessible = False
                
                if owner_type == 'photographer':
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    is_accessible = (photographer and str(photographer.user_id) == user_id)
                    
                elif owner_type == 'room':
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == owner_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        is_accessible = (studio and str(studio.user_id) == user_id)

                if not is_accessible:
                    return [], 0
        
        # Получение общего количества
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        exceptions = result.scalars().all()

        return list(exceptions), total

    @staticmethod
    async def update_exception(
        db: AsyncSession,
        exception_id: int,
        updates: dict,
        user_id: Optional[str] = None
    ) -> Any:
        """Обновляет исключение из расписания.
        
        Args:
            db: Асинхронная сессия базы данных
            exception_id: ID исключения для обновления
            updates: Словарь с полями для обновления
            user_id: ID текущего пользователя
            
        Returns:
            Обновленная запись исключения
        """
        from app.models.shesuleexception import ScheduleException
        
        result = await db.execute(
            select(ScheduleException).where(ScheduleException.id == exception_id)
        )
        exception = result.scalar_one_or_none()

        if not exception:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Исключение из расписания с ID {exception_id} не найдено"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if exception.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == exception.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif exception.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == exception.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на обновление этого исключения"
                    )

        # Валидация обновляемых полей
        if 'is_day_off' in updates and 'custom_start_time' in updates:
            if updates['is_day_off'] and updates['custom_start_time']:
                raise ScheduleValidationError(
                    status_code=400,
                    detail="Для дня выходного нельзя указывать кастомное время"
                )
        
        if not updates.get('is_day_off') and ('custom_start_time' in updates or 'custom_end_time' in updates):
            custom_start = updates.get('custom_start_time', exception.custom_start_time)
            custom_end = updates.get('custom_end_time', exception.custom_end_time)
            
            if custom_start and custom_end:
                validate_time_range(custom_start, custom_end)

        # Применение обновлений
        for field, value in updates.items():
            if hasattr(exception, field):
                setattr(exception, field, value)

        await db.commit()
        await db.refresh(exception)

        return exception

    @staticmethod
    async def delete_exception(
        db: AsyncSession, 
        exception_id: int, 
        user_id: Optional[str] = None
    ) -> bool:
        """Удаляет исключение из расписания.
        
        Args:
            db: Асинхронная сессия базы данных
            exception_id: ID исключения для удаления
            user_id: ID текущего пользователя
            
        Returns:
            True если успешно удалено
        """
        from app.models.shesuleexception import ScheduleException
        
        result = await db.execute(
            select(ScheduleException).where(ScheduleException.id == exception_id)
        )
        exception = result.scalar_one_or_none()

        if not exception:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Исключение из расписания с ID {exception_id} не найдено"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if exception.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == exception.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif exception.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == exception.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на удаление этого исключения"
                    )

        await db.delete(exception)
        await db.commit()

        return True


# ============================================================================
# Schedule Block Service (для блокировки слотов)
# ============================================================================

class ScheduleBlockService:
    """Сервис для управления блокировками временных слотов."""

    @staticmethod
    async def create_block(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        start_datetime: date,
        end_datetime: date,
        reason: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Any:
        """Создаёт блокировку временного слота.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца
            owner_type: Тип владельца
            start_datetime: Дата начала блокировки
            end_datetime: Дата окончания блокировки
            reason: Причина блокировки (опционально)
            user_id: ID текущего пользователя
            
        Returns:
            Созданная запись блокировки
            
        Raises:
            ScheduleValidationError: Если данные некорректны или есть пересечения
            ScheduleConflictError: Если блокировка пересекается с существующей
            ScheduleAccessDeniedError: Если нет прав на создание
            ScheduleNotFoundError: Если владелец не найден
        """
        # Валидация дат
        validate_date_range(start_datetime, end_datetime)

        # Проверка существования владельца и прав доступа
        if owner_type == 'photographer':
            from app.models.photographerprofile import PhotographerProfile
            result = await db.execute(
                select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
            )
            owner = result.scalar_one_or_none()
            
            if user_id and owner:
                if str(owner.user_id) != user_id:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Фотограф может блокировать только своё расписание"
                    )
        elif owner_type == 'room':
            from app.models.studioroom import StudioRoom
            result = await db.execute(
                select(StudioRoom).where(StudioRoom.id == owner_id)
            )
            room = result.scalar_one_or_none()
            
            if user_id and room:
                from app.models.studioprofile import StudioProfile
                studio_result = await db.execute(
                    select(StudioProfile).where(StudioProfile.id == room.studio_id)
                )
                studio = studio_result.scalar_one_or_none()
                
                from app.models.user import User
                user_result = await db.execute(select(User).where(User.id == user_id))
                current_user = user_result.scalar_one_or_none()
                
                if current_user and (current_user.role != 'studio' or 
                                     str(current_user.studio_profile_id) != str(room.studio_id)):
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="Представитель студии может блокировать только свои залы"
                    )
        else:
            raise ScheduleValidationError(
                status_code=400,
                detail="Некорректный тип владельца"
            )

        if not owner and not room:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Владелец (owner_id={owner_id}, type={owner_type}) не найден"
            )

        # Проверка на пересечения с существующими блокировками
        from app.models.sheduletemplate import ScheduleTemplate
        
        check_query = select(ScheduleBlock).where(
            or_(
                and_(ScheduleBlock.photographer_id == owner_id, 
                     ScheduleBlock.room_id.is_(None)),
                and_(ScheduleBlock.room_id == owner_id, 
                     ScheduleBlock.photographer_id.is_(None))
            ),
            or_(
                # Пересечение по датам
                and_(
                    ScheduleBlock.start_datetime <= end_datetime,
                    ScheduleBlock.end_datetime >= start_datetime
                )
            )
        )
        
        check_result = await db.execute(check_query)
        existing_blocks = check_result.scalars().all()
        
        if existing_blocks:
            raise ScheduleConflictError(
                status_code=409,
                detail="Новая блокировка пересекается с существующей блокировкой"
            )

        # Создание записи блокировки
        block = ScheduleBlock(
            photographer_id=owner_id if owner_type == 'photographer' else None,
            room_id=owner_id if owner_type == 'room' else None,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            reason=reason,
        )
        
        db.add(block)
        await db.commit()
        await db.refresh(block)

        return block

    @staticmethod
    async def get_block(
        db: AsyncSession, 
        block_id: int,
        user_id: Optional[str] = None
    ) -> Any:
        """Получает блокировку по ID.
        
        Args:
            db: Асинхронная сессия базы данных
            block_id: ID блокировки
            user_id: ID текущего пользователя
            
        Returns:
            Запись блокировки или None если не найдена/нет прав
        """
        from app.models.sheduletemplate import ScheduleBlock
        
        result = await db.execute(
            select(ScheduleBlock).where(ScheduleBlock.id == block_id)
        )
        block = result.scalar_one_or_none()

        if not block:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Блокировка слота с ID {block_id} не найдена"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if block.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == block.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif block.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == block.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на просмотр этой блокировки"
                    )

        return block

    @staticmethod
    async def get_blocks_by_owner(
        db: AsyncSession,
        owner_id: int,
        owner_type: str,
        user_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Any], int]:
        """Получает список блокировок для владельца.
        
        Args:
            db: Асинхронная сессия базы данных
            owner_id: ID владельца
            owner_type: Тип владельца
            user_id: ID текущего пользователя
            date_from: Фильтр по дате начала
            date_to: Фильтр по дате окончания
            skip: Количество записей для пропуска
            limit: Максимальное количество записей
            
        Returns:
            Кортеж из списка блокировок и общего количества
        """
        from app.models.sheduletemplate import ScheduleBlock
        
        query = select(ScheduleBlock).where(
            or_(
                and_(ScheduleBlock.photographer_id == owner_id, ScheduleBlock.room_id.is_(None)),
                and_(ScheduleBlock.room_id == owner_id, ScheduleBlock.photographer_id.is_(None))
            )
        )

        if date_from:
            query = query.where(ScheduleBlock.start_datetime >= date_from)
        
        if date_to:
            query = query.where(ScheduleBlock.end_datetime <= date_to)

        # Проверка прав доступа
        if user_id:
            from app.models.user import User
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_accessible = False
                
                if owner_type == 'photographer':
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == owner_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    is_accessible = (photographer and str(photographer.user_id) == user_id)
                    
                elif owner_type == 'room':
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == owner_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        is_accessible = (studio and str(studio.user_id) == user_id)

                if not is_accessible:
                    return [], 0
        
        # Получение общего количества
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        blocks = result.scalars().all()

        return list(blocks), total

    @staticmethod
    async def delete_block(
        db: AsyncSession, 
        block_id: int, 
        user_id: Optional[str] = None
    ) -> bool:
        """Удаляет блокировку слота.
        
        Args:
            db: Асинхронная сессия базы данных
            block_id: ID блокировки для удаления
            user_id: ID текущего пользователя
            
        Returns:
            True если успешно удалена
        """
        from app.models.sheduletemplate import ScheduleBlock
        
        result = await db.execute(
            select(ScheduleBlock).where(ScheduleBlock.id == block_id)
        )
        block = result.scalar_one_or_none()

        if not block:
            raise ScheduleNotFoundError(
                status_code=404,
                detail=f"Блокировка слота с ID {block_id} не найдена"
            )

        # Проверка прав доступа
        from app.models.user import User
        
        if user_id:
            user_result = await db.execute(select(User).where(User.id == user_id))
            current_user = user_result.scalar_one_or_none()
            
            if current_user and current_user.role != 'admin':
                is_owner = False
                
                if block.photographer_id:
                    from app.models.photographerprofile import PhotographerProfile
                    ph_result = await db.execute(
                        select(PhotographerProfile).where(PhotographerProfile.id == block.photographer_id)
                    )
                    photographer = ph_result.scalar_one_or_none()
                    if photographer and str(photographer.user_id) == user_id:
                        is_owner = True
                
                elif block.room_id:
                    from app.models.studioroom import StudioRoom
                    room_result = await db.execute(
                        select(StudioRoom).where(StudioRoom.id == block.room_id)
                    )
                    room = room_result.scalar_one_or_none()
                    
                    if room and current_user.role == 'studio':
                        from app.models.studioprofile import StudioProfile
                        studio_result = await db.execute(
                            select(StudioProfile).where(StudioProfile.id == room.studio_id)
                        )
                        studio = studio_result.scalar_one_or_none()
                        
                        if studio and str(studio.user_id) == user_id:
                            is_owner = True
                
                if not is_owner:
                    raise ScheduleAccessDeniedError(
                        status_code=403,
                        detail="У вас нет прав на удаление этой блокировки"
                    )

        await db.delete(block)
        await db.commit()

        return True


# ============================================================================
# Initialize ScheduleBlock model if not exists
# ============================================================================

async def init_schedule_block_model(db: AsyncSession):
    """Инициализирует модель ScheduleBlock если она ещё не создана.
    
    Эта функция должна быть вызвана один раз при инициализации БД.
    
    Args:
        db: Асинхронная сессия базы данных
    """
    from app.models.base import Base
    
    # Проверяем, существует ли таблица schedule_blocks
    from sqlalchemy import inspect
    inspector = await db.run_sync(inspect)
    
    if 'schedule_blocks' not in inspector.get_table_names():
        # Создаём модель ScheduleBlock динамически
        from datetime import time as time_type
        from sqlalchemy import TIME, CheckConstraint
        
        class ScheduleBlock(Base):
            __tablename__ = "schedule_blocks"

            id: int = 0  # Placeholder for type checker
            photographer_id: Optional[int] = None
            room_id: Optional[int] = None
            start_datetime: date = None
            end_datetime: date = None
            reason: Optional[str] = None

        # Создаём таблицу через MetaData
        from sqlalchemy import MetaData
        
        metadata = Base.metadata
        
        # Создаём таблицу schedule_blocks если её нет
        from sqlalchemy.schema import CreateTable
        
        await db.execute(CreateTable(ScheduleBlock.__table__, checkfirst=True))
        
        await db.commit()
