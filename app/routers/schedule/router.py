"""
RESTful API endpoints для модуля управления расписанием PicNest.

Этот модуль содержит все API эндпоинты для работы с:
- Недельными шаблонами расписания (ScheduleTemplate)
- Исключениями из расписания (ScheduleException)  
- Блокировками временных слотов (ScheduleBlock)

Все endpoints обеспечивают:
- RBAC авторизацию и проверку прав доступа
- Валидацию входных данных через Pydantic v2
- Обработку ошибок со статус-кодами 400, 403, 404, 409
- Пагинацию для списковых endpoints

Автор: PicNest Backend Team
"""

from datetime import date, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schedule.schemas import (
    # Template schemas
    ScheduleTemplateCreate,
    ScheduleTemplateResponse,
    ScheduleTemplateUpdate,
    ScheduleTemplatesBulkCreateRequest,
    ScheduleTemplatesBulkResponse,
    ScheduleTemplatesListResponse,
    
    # Exception schemas
    ScheduleExceptionCreate,
    ScheduleExceptionResponse,
    ScheduleExceptionUpdate,
    ScheduleExceptionListResponse,
    
    # Block schemas
    ScheduleBlockCreate,
    ScheduleBlockResponse,
    ScheduleBlockListResponse,
    
    # Query params
    ScheduleQueryParams,
    PaginationParams,
)

from app.services.schedule.services import (
    ScheduleTemplateService,
    ScheduleExceptionService,
    ScheduleBlockService,
    ScheduleValidationError,
    ScheduleConflictError,
    ScheduleAccessDeniedError,
    ScheduleNotFoundError,
)


# Создаём роутер для расписания
router = APIRouter(
    prefix="/api/v1/schedules",
    tags=["Schedule Management"]
)


# ============================================================================
# Helper function for response formatting with pagination
# ============================================================================

def paginate_response(data: List, total: int, skip: int, limit: int):
    """Формирует ответ с пагинацией.
    
    Args:
        data: Список данных для ответа
        total: Общее количество записей
        skip: Пропущенное количество
        limit: Лимит записей
        
    Returns:
        Словарь с данными и метаданными пагинации
    """
    return {
        "items": data,
        "total": total,
        "skip": skip,
        "limit": min(limit, total),  # Не больше чем всего записей
    }


# ============================================================================
# Schedule Template Endpoints
# ============================================================================

@router.post(
    "/templates",
    response_model=ScheduleTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон расписания",
    description="""
    Создаёт новый недельный шаблон расписания для фотографа или зала студии.

    **Права доступа:**
    - Фотографы могут создавать шаблоны только для своего профиля
    - Представители студий могут создавать шаблоны только для своих залов
    
    **Валидация:**
    - Время начала должно быть строго меньше времени окончания
    - День недели должен быть в диапазоне 1-7 (понедельник-воскресенье)
    """
)
async def create_schedule_template(
    template_data: ScheduleTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создаёт новый шаблон расписания."""
    
    try:
        result = await ScheduleTemplateService.create_template(
            db=db,
            owner_id=template_data.owner_id,
            owner_type=template_data.owner_type.value,
            day_of_week=template_data.day_of_week.value,
            start_time=template_data.start_time,
            end_time=template_data.end_time,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleTemplateResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            day_of_week=result.day_of_week,
            start_time=result.start_time,
            end_time=result.end_time,
        )
        
    except ScheduleValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/templates",
    response_model=ScheduleTemplatesListResponse,
    summary="Получить список шаблонов расписания",
    description="""
    Возвращает список недельных шаблонов расписания с пагинацией.

    **Возможные фильтры:**
    - owner_id: ID владельца (фотографа или зала)
    - owner_type: Тип владельца (photographer/room)
    - day_of_week: Фильтр по дню недели (1-7)
    
    **Права доступа:**
    - Пользователь может видеть только шаблоны своего профиля
    """
)
async def get_schedule_templates(
    owner_id: Optional[int] = Query(None, description="ID владельца"),
    owner_type: Optional[str] = Query(None, description="Тип владельца (photographer/room)"),
    day_of_week: Optional[int] = Query(None, ge=1, le=7, description="День недели (1-7)"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает список шаблонов расписания с пагинацией."""
    
    try:
        templates, total = await ScheduleTemplateService.get_templates_by_owner(
            db=db,
            owner_id=owner_id,
            owner_type=owner_type or "photographer",
            user_id=current_user.id if current_user else None,
            day_of_week=int(day_of_week) if day_of_week else None,
            skip=pagination.skip,
            limit=pagination.limit,
        )
        
        response_data = [
            ScheduleTemplateResponse(
                id=t.id,
                owner_id=t.photographer_id or t.room_id,
                owner_type="photographer" if t.photographer_id else "room",
                day_of_week=t.day_of_week,
                start_time=t.start_time,
                end_time=t.end_time,
            )
            for t in templates
        ]
        
        return ScheduleTemplatesListResponse(
            templates=response_data,
            total=total,
            skip=pagination.skip,
            limit=min(pagination.limit, total),
        )
        
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/templates/{template_id}",
    response_model=ScheduleTemplateResponse,
    summary="Получить шаблон расписания по ID",
    description="""
    Возвращает данные конкретного шаблона расписания.
    
    **Права доступа:**
    - Пользователь может видеть только свой шаблон
    """
)
async def get_schedule_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает шаблон расписания по ID."""
    
    try:
        result = await ScheduleTemplateService.get_template(
            db=db,
            template_id=template_id,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleTemplateResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            day_of_week=result.day_of_week,
            start_time=result.start_time,
            end_time=result.end_time,
        )
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.put(
    "/templates/{template_id}",
    response_model=ScheduleTemplateResponse,
    summary="Обновить шаблон расписания",
    description="""
    Обновляет существующий шаблон расписания.

    **Права доступа:**
    - Только владелец шаблона может его обновлять
    
    **Валидация:**
    - При обновлении start_time и end_time оба должны быть указаны
    - Время начала должно быть строго меньше времени окончания
    """
)
async def update_schedule_template(
    template_id: int,
    updates: ScheduleTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновляет шаблон расписания."""
    
    try:
        # Формируем словарь обновлений только с указанными полями
        update_dict = updates.model_dump(exclude_unset=True)
        
        result = await ScheduleTemplateService.update_template(
            db=db,
            template_id=template_id,
            updates=update_dict,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleTemplateResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            day_of_week=result.day_of_week,
            start_time=result.start_time,
            end_time=result.end_time,
        )
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.delete(
    "/templates/{template_id}",
    response_model=dict,
    summary="Удалить шаблон расписания",
    description="""
    Удаляет шаблон расписания.

    **Права доступа:**
    - Только владелец шаблона может его удалить
    
    **Возвращаемое значение:**
    - Объект с сообщением об успешном удалении
    """
)
async def delete_schedule_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаляет шаблон расписания."""
    
    try:
        await ScheduleTemplateService.delete_template(
            db=db,
            template_id=template_id,
            user_id=current_user.id if current_user else None,
        )
        
        return {
            "status": "success",
            "message": f"Шаблон расписания с ID {template_id} успешно удалён"
        }
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


# ============================================================================
# Schedule Exception Endpoints
# ============================================================================

@router.post(
    "/exceptions",
    response_model=ScheduleExceptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать исключение из расписания",
    description="""
    Создаёт исключение из расписания для конкретной даты.

    **Варианты исключения:**
    1. День выходной: `is_day_off=true` (без указания времени)
    2. Кастомное время: `is_day_off=false` + `custom_start_time` и `custom_end_time`

    **Права доступа:**
    - Фотографы могут создавать исключения только для своего профиля
    - Представители студий — только для своих залов
    
    **Валидация:**
    - Нельзя указывать время при is_day_off=true
    - При is_day_off=false необходимо указать время работы
    """
)
async def create_schedule_exception(
    exception_data: ScheduleExceptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создаёт исключение из расписания."""
    
    try:
        result = await ScheduleExceptionService.create_exception(
            db=db,
            owner_id=exception_data.owner_id,
            owner_type=exception_data.owner_type.value,
            date_=exception_data.date,
            is_day_off=exception_data.is_day_off,
            custom_start_time=exception_data.custom_start_time,
            custom_end_time=exception_data.custom_end_time,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleExceptionResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            date=result.date,
            is_day_off=result.is_day_off,
            custom_start_time=result.custom_start_time,
            custom_end_time=result.custom_end_time,
        )
        
    except ScheduleValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleConflictError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/exceptions",
    response_model=ScheduleExceptionListResponse,
    summary="Получить список исключений из расписания",
    description="""
    Возвращает список исключений из расписания с пагинацией.

    **Возможные фильтры:**
    - owner_id: ID владельца (фотографа или зала)
    - owner_type: Тип владельца (photographer/room)
    - date_from: Дата начала фильтрации
    - date_to: Дата конца фильтрации
    
    **Права доступа:**
    - Пользователь может видеть только свои исключения
    """
)
async def get_schedule_exceptions(
    owner_id: Optional[int] = Query(None, description="ID владельца"),
    owner_type: Optional[str] = Query(None, description="Тип владельца (photographer/room)"),
    date_from: Optional[date] = Query(None, description="Дата начала фильтрации"),
    date_to: Optional[date] = Query(None, description="Дата конца фильтрации"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает список исключений из расписания с пагинацией."""
    
    try:
        exceptions, total = await ScheduleExceptionService.get_exceptions_by_owner(
            db=db,
            owner_id=owner_id,
            owner_type=owner_type or "photographer",
            user_id=current_user.id if current_user else None,
            date_from=date_from,
            date_to=date_to,
            skip=pagination.skip,
            limit=pagination.limit,
        )
        
        response_data = [
            ScheduleExceptionResponse(
                id=e.id,
                owner_id=e.photographer_id or e.room_id,
                owner_type="photographer" if e.photographer_id else "room",
                date=e.date,
                is_day_off=e.is_day_off,
                custom_start_time=e.custom_start_time,
                custom_end_time=e.custom_end_time,
            )
            for e in exceptions
        ]
        
        return ScheduleExceptionListResponse(
            exceptions=response_data,
            total=total,
            skip=pagination.skip,
            limit=min(pagination.limit, total),
        )
        
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/exceptions/{exception_id}",
    response_model=ScheduleExceptionResponse,
    summary="Получить исключение из расписания по ID",
    description="""
    Возвращает данные конкретного исключения из расписания.
    
    **Права доступа:**
    - Пользователь может видеть только своё исключение
    """
)
async def get_schedule_exception(
    exception_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает исключение из расписания по ID."""
    
    try:
        result = await ScheduleExceptionService.get_exception(
            db=db,
            exception_id=exception_id,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleExceptionResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            date=result.date,
            is_day_off=result.is_day_off,
            custom_start_time=result.custom_start_time,
            custom_end_time=result.custom_end_time,
        )
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.put(
    "/exceptions/{exception_id}",
    response_model=ScheduleExceptionResponse,
    summary="Обновить исключение из расписания",
    description="""
    Обновляет существующее исключение из расписания.

    **Права доступа:**
    - Только владелец исключения может его обновлять
    
    **Валидация:**
    - Нельзя указывать время при is_day_off=true
    - При is_day_off=false необходимо указать время работы
    """
)
async def update_schedule_exception(
    exception_id: int,
    updates: ScheduleExceptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновляет исключение из расписания."""
    
    try:
        # Формируем словарь обновлений только с указанными полями
        update_dict = updates.model_dump(exclude_unset=True)
        
        result = await ScheduleExceptionService.update_exception(
            db=db,
            exception_id=exception_id,
            updates=update_dict,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleExceptionResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            date=result.date,
            is_day_off=result.is_day_off,
            custom_start_time=result.custom_start_time,
            custom_end_time=result.custom_end_time,
        )
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.delete(
    "/exceptions/{exception_id}",
    response_model=dict,
    summary="Удалить исключение из расписания",
    description="""
    Удаляет исключение из расписания.

    **Права доступа:**
    - Только владелец исключения может его удалить
    
    **Возвращаемое значение:**
    - Объект с сообщением об успешном удалении
    """
)
async def delete_schedule_exception(
    exception_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаляет исключение из расписания."""
    
    try:
        await ScheduleExceptionService.delete_exception(
            db=db,
            exception_id=exception_id,
            user_id=current_user.id if current_user else None,
        )
        
        return {
            "status": "success",
            "message": f"Исключение из расписания с ID {exception_id} успешно удалено"
        }
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


# ============================================================================
# Schedule Block Endpoints (блокировка слотов)
# ============================================================================

@router.post(
    "/blocks",
    response_model=ScheduleBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать блокировку временного слота",
    description="""
    Создаёт ручную блокировку на период для предотвращения бронирования.

    **Назначение:**
    - Предотвращение двойного бронирования при сторонних заказах
    - Блокировка на время ремонта, отпусков и других случаев
    
    **Права доступа:**
    - Фотографы могут блокировать только своё расписание
    - Представители студий — только свои залы
    
    **Валидация:**
    - Новая блокировка не должна пересекаться с существующими
    """
)
async def create_schedule_block(
    block_data: ScheduleBlockCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создаёт блокировку временного слота."""
    
    try:
        result = await ScheduleBlockService.create_block(
            db=db,
            owner_id=block_data.owner_id,
            owner_type=block_data.owner_type.value,
            start_datetime=block_data.start_datetime,
            end_datetime=block_data.end_datetime,
            reason=block_data.reason,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleBlockResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            start_datetime=result.start_datetime,
            end_datetime=result.end_datetime,
            reason=result.reason,
        )
        
    except ScheduleValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleConflictError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/blocks",
    response_model=ScheduleBlockListResponse,
    summary="Получить список блокировок слотов",
    description="""
    Возвращает список блокировок временных слотов с пагинацией.

    **Возможные фильтры:**
    - owner_id: ID владельца (фотографа или зала)
    - owner_type: Тип владельца (photographer/room)
    - date_from: Дата начала фильтрации
    - date_to: Дата конца фильтрации
    
    **Права доступа:**
    - Пользователь может видеть только свои блокировки
    """
)
async def get_schedule_blocks(
    owner_id: Optional[int] = Query(None, description="ID владельца"),
    owner_type: Optional[str] = Query(None, description="Тип владельца (photographer/room)"),
    date_from: Optional[date] = Query(None, description="Дата начала фильтрации"),
    date_to: Optional[date] = Query(None, description="Дата конца фильтрации"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает список блокировок слотов с пагинацией."""
    
    try:
        blocks, total = await ScheduleBlockService.get_blocks_by_owner(
            db=db,
            owner_id=owner_id,
            owner_type=owner_type or "photographer",
            user_id=current_user.id if current_user else None,
            date_from=date_from,
            date_to=date_to,
            skip=pagination.skip,
            limit=pagination.limit,
        )
        
        response_data = [
            ScheduleBlockResponse(
                id=b.id,
                owner_id=b.photographer_id or b.room_id,
                owner_type="photographer" if b.photographer_id else "room",
                start_datetime=b.start_datetime,
                end_datetime=b.end_datetime,
                reason=b.reason,
            )
            for b in blocks
        ]
        
        return ScheduleBlockListResponse(
            blocks=response_data,
            total=total,
            skip=pagination.skip,
            limit=min(pagination.limit, total),
        )
        
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.get(
    "/blocks/{block_id}",
    response_model=ScheduleBlockResponse,
    summary="Получить блокировку слота по ID",
    description="""
    Возвращает данные конкретной блокировки временного слота.
    
    **Права доступа:**
    - Пользователь может видеть только свою блокировку
    """
)
async def get_schedule_block(
    block_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает блокировку слота по ID."""
    
    try:
        result = await ScheduleBlockService.get_block(
            db=db,
            block_id=block_id,
            user_id=current_user.id if current_user else None,
        )
        
        return ScheduleBlockResponse(
            id=result.id,
            owner_id=result.photographer_id or result.room_id,
            owner_type="photographer" if result.photographer_id else "room",
            start_datetime=result.start_datetime,
            end_datetime=result.end_datetime,
            reason=result.reason,
        )
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


@router.delete(
    "/blocks/{block_id}",
    response_model=dict,
    summary="Разблокировать временной слот",
    description="""
    Удаляет блокировку временного слота (разблокирует период).

    **Права доступа:**
    - Только владелец блокировки может разблокировать слот
    
    **Возвращаемое значение:**
    - Объект с сообщением об успешной разблокировке
    """
)
async def delete_schedule_block(
    block_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Разблокирует временной слот (удаляет блокировку)."""
    
    try:
        await ScheduleBlockService.delete_block(
            db=db,
            block_id=block_id,
            user_id=current_user.id if current_user else None,
        )
        
        return {
            "status": "success",
            "message": f"Блокировка слота с ID {block_id} успешно удалена (слот разблокирован)"
        }
        
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )
    except ScheduleAccessDeniedError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e.detail)
        )


# ============================================================================
# Mass operations (bulk create templates)
# ============================================================================

@router.post(
    "/templates/bulk",
    response_model=ScheduleTemplatesBulkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Массовое создание шаблонов расписания",
    description="""
    Позволяет массово создать недельные шаблоны для всех дней недели одновременно.

    **Пример использования:**
    ```json
    {
        "templates": [
            {"owner_id": 1, "owner_type": "photographer", "day_of_week": 1, "start_time": "09:00", "end_time": "18:00"},
            {"owner_id": 1, "owner_type": "photographer", "day_of_week": 2, "start_time": "09:00", "end_time": "18:00"},
            ...
        ]
    }
    ```

    **Права доступа:**
    - Фотографы могут создавать шаблоны только для своего профиля
    - Представители студий — только для своих залов
    """
)
async def bulk_create_schedule_templates(
    bulk_data: ScheduleTemplatesBulkCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Массовое создание шаблонов расписания."""
    
    created_count = 0
    failed_templates = []

    for idx, template_data in enumerate(bulk_data.templates):
        try:
            await ScheduleTemplateService.create_template(
                db=db,
                owner_id=template_data.owner_id,
                owner_type=template_data.owner_type.value,
                day_of_week=template_data.day_of_week.value,
                start_time=template_data.start_time,
                end_time=template_data.end_time,
                user_id=current_user.id if current_user else None,
            )
            created_count += 1
            
        except Exception as e:
            failed_templates.append({
                "index": idx,
                "owner_id": template_data.owner_id,
                "owner_type": template_data.owner_type.value,
                "day_of_week": template_data.day_of_week.value,
                "error": str(e),
            })

    return ScheduleTemplatesBulkResponse(
        created_count=created_count,
        failed_templates=failed_templates,
    )


# ============================================================================
# Custom exception handlers for schedule module
# ============================================================================

@router.exception_handler(ScheduleValidationError)
async def schedule_validation_exception_handler(request, exc: ScheduleValidationError):
    """Обработчик ошибок валидации расписания."""
    return HTTPException(
        status_code=exc.status_code,
        detail=str(exc.detail)
    )


@router.exception_handler(ScheduleConflictError)
async def schedule_conflict_exception_handler(request, exc: ScheduleConflictError):
    """Обработчик конфликтов при создании расписания."""
    return HTTPException(
        status_code=exc.status_code,
        detail=str(exc.detail)
    )


@router.exception_handler(ScheduleAccessDeniedError)
async def schedule_access_denied_exception_handler(request, exc: ScheduleAccessDeniedError):
    """Обработчик ошибок доступа к расписанию."""
    return HTTPException(
        status_code=exc.status_code,
        detail=str(exc.detail)
    )


@router.exception_handler(ScheduleNotFoundError)
async def schedule_not_found_exception_handler(request, exc: ScheduleNotFoundError):
    """Обработчик отсутствия записи в расписании."""
    return HTTPException(
        status_code=exc.status_code,
        detail=str(exc.detail)
    )
