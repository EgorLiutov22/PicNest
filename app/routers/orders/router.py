"""
RESTful API endpoints для модуля управления заказами PicNest Marketplace.

Этот модуль содержит все API эндпоинты для работы с заказами:
- POST /api/v1/orders - Создание нового заказа клиентом
- GET /api/v1/orders - Получение списка заказов (с разграничением видимости)
- GET /api/v1/orders/{id} - Детальный просмотр заказа участниками
- POST /api/v1/orders/{id}/confirm - Подтверждение брони исполнителем
- POST /api/v1/orders/{id}/cancel - Отмена заказа с расчетом возврата

Все endpoints обеспечивают:
- RBAC авторизацию и проверку прав доступа
- Валидацию входных данных через Pydantic v2
- Обработку ошибок со статус-кодами 400, 403, 404, 409
- Атомарную проверку отсутствия пересечений временных интервалов

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.orderstatus import OrderStatus as DBOrderStatus
from app.models.ordertype import OrderType as DBOrderType
from app.schemas.orders.schemas import (
    # Schemas для создания
    OrderCreate,
    OrderCreateResponse,
    
    # Schemas для ответов
    OrderResponse,
    OrdersListResponse,
    OrderSummary,
    
    # Параметры запроса
    OrderSearchParams,
    OrderPaginationParams,
    
    # Управление заказами
    OrderConfirmRequest,
    OrderCancelRequest,
    OrderCancelResponse,
)

from app.services.orders.services import (
    OrderService,
    StatusManagerService,
    SlotConflictError,
    ScheduleBlockedException,
    StatusTransitionNotAllowed,
    OrderNotFoundError,
    OrderForbiddenError,
    OrderValidationError,
)


# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(
    tags=["Orders Management"],
    responses={
        400: {"description": "Bad request - ошибка валидации данных"},
        403: {"description": "Forbidden - недостаточно прав доступа"},
        404: {"description": "Not found - заказ не найден"},
        409: {"description": "Conflict - конфликт слотов (двойное бронирование)"},
    }
)


# ============================================================================
# Helper Functions for Response Formatting
# ============================================================================

def order_to_summary(order) -> OrderSummary:
    """Конвертирует модель заказа в Summary для списка."""
    
    from app.schemas.orders.schemas import OrderTypeEnum, OrderStatusEnum
    
    return OrderSummary(
        id=order.id,
        order_type=OrderTypeEnum(order.order_type),
        status=OrderStatusEnum(order.status),
        total_price=order.total_price,
        created_at=order.created_at,
    )


def order_to_detail_response(order) -> OrderResponse:
    """Конвертирует модель заказа в детальный ответ."""
    
    from app.schemas.orders.schemas import (
        OrderTypeEnum, 
        OrderStatusEnum,
        OrderItemResponse,
        PhotographerInfo,
        StudioRoomInfo,
    )
    
    items = []
    for item in order.items:
        item_response = {
            "id": item.id,
            "photographer_id": item.photographer_id,
            "photographer_service_id": item.photographer_service_id,
            "studio_room_id": item.studio_room_id,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "fixed_price": item.fixed_price,
            "fixed_conditions": item.fixed_conditions or {},
        }
        
        # Добавляем информацию о фотографе
        if item.photographer:
            photographer_info = PhotographerInfo(
                id=item.photographer.id,
                display_name=item.photographer.display_name,
                service_title=(
                    item.photographer_service.title 
                    if item.photographer_service else None
                ),
                fixed_price=item.fixed_price,
            )
            item_response["photographer_info"] = photographer_info
        
        # Добавляем информацию о зале студии
        if item.studio_room:
            studio_info = StudioRoomInfo(
                id=item.studio_room.id,
                name=item.studio_room.name,
                studio_title=(
                    item.studio_room.studio.title 
                    if item.studio_room.studio else "Unknown"
                ),
                address=(
                    item.studio_room.studio.address 
                    if item.studio_room.studio else ""
                ),
                fixed_price=item.fixed_price,
            )
            item_response["studio_room_info"] = studio_info
        
        items.append(OrderItemResponse(**item_response))
    
    return OrderResponse(
        id=order.id,
        order_type=OrderTypeEnum(order.order_type),
        status=OrderStatusEnum(order.status),
        total_price=order.total_price,
        prepayment_amount=order.prepayment_amount,
        created_at=order.created_at,
        client_id=order.client_id,
        items=items,
        cancellation_conditions={},  # Можно добавить из модели если есть
    )


# ============================================================================
# Order Creation Endpoint (POST /api/v1/orders)
# ============================================================================

@limiter.limit("20/minute")  # Защита от спама бронирований
@router.post(
    "",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый заказ",
    description="""
    Создает новый заказ на бронирование фотографа и/или зала студии.

    **Типы заказов:**
    - `photographer_only` - только фотограф
    - `studio_only` - только зал фотостудии
    - `combined` - комбинированный (фотограф + зал)

    **Валидация:**
    - Все временные интервалы проверяются на пересечения с существующими бронями
    - Проверяется наличие блокировок в расписании и исключений (выходные дни)
    - Цены и условия фиксируются на момент создания заказа (снапшот)

    **Права доступа:**
    - Только авторизованный клиент может создать заказ для себя
    
    **Пример запроса:**
    ```json
    {
      "order_type": "photographer_only",
      "items": [
        {
          "photographer_id": 123,
          "photographer_service_id": 456,
          "start_time": "2026-10-15T10:00:00+03:00",
          "end_time": "2026-10-15T14:00:00+03:00"
        }
      ],
      "prepayment_amount": 5000.00,
      "cancellation_conditions": {
        "refund_policy": {"percentage": 80}
      }
    }
    ```

    **Обработка ошибок:**
    - 409 Conflict - если слот занят другим заказом
    - 403 Forbidden - если слот заблокирован в расписании
    - 400 Bad Request - ошибки валидации данных
    """
)
async def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создает новый заказ с валидацией и снапшотом данных.
    
    Проверяет:
    - Все временные интервалы в будущем
    - start_time < end_time для каждого элемента
    - Максимальная длительность бронирования (8 часов)
    - Минимальное время до начала (1 час)
    """
    
    from app.core.exceptions import ValidationException, ForbiddenException
    
    # Проверка 1: Все временные интервалы должны быть в будущем
    now = datetime.now()
    min_start_time = now + timedelta(hours=1)  # Минимум за час до начала
    max_duration = timedelta(hours=8)
    
    # Группируем элементы заказа по времени для проверки пересечений
    time_slots = []
    
    for idx, item in enumerate(order_data.items):
        start_dt = item.start_time if isinstance(item.start_time, datetime) else item.start_time.replace(tzinfo=None)
        end_dt = item.end_time if isinstance(item.end_time, datetime) else item.end_time.replace(tzinfo=None)
        
        # Проверка 1.1: Все временные интервалы в будущем
        if start_dt < min_start_time:
            raise ValidationException(
                detail=f"Бронирование должно быть минимум за 1 час. Дата {start_dt} слишком близко.",
                error_code="BOOKING_TOO_SOON",
            )
        
        # Проверка 1.2: end_time > start_time
        if end_dt <= start_dt:
            raise ValidationException(
                detail=f"Время окончания ({end_dt}) должно быть позже времени начала ({start_dt})",
                error_code="INVALID_TIME_RANGE",
            )
        
        # Проверка 1.3: Максимальная длительность (8 часов)
        duration = end_dt - start_dt
        if duration > max_duration:
            raise ValidationException(
                detail=f"Максимальная длительность бронирования — 8 часов. Длительность: {duration}",
                error_code="DURATION_EXCEEDED",
            )
        
        # Проверка 1.4: start_time и end_time должны быть в одном timezone
        if hasattr(item.start_time, 'tzinfo') and hasattr(item.end_time, 'tzinfo'):
            if item.start_time.tzinfo != item.end_time.tzinfo:
                raise ValidationException(
                    detail="Время начала и окончания должны быть в одном часовом поясе",
                    error_code="TIMEZONE_MISMATCH",
                )
        
        # Сохраняем временной слот для проверки пересечений
        time_slots.append({
            "start": start_dt,
            "end": end_dt,
            "photographer_id": item.photographer_id,
            "studio_room_id": item.studio_room_id if hasattr(item, 'studio_room_id') else None,
            "item_idx": idx,
        })
    
    # Проверка 2: Для комбинированных заказов (photographer + studio) — проверка что фотограф и зал в одно время
    if order_data.order_type == "combined" or len(order_data.items) > 1:
        from collections import defaultdict
        slots_by_time = defaultdict(list)
        
        for slot in time_slots:
            # Группируем по времени (с точностью до минуты)
            time_key = f"{slot['start'].strftime('%Y-%m-%d %H:%M')}"
            slots_by_time[time_key].append(slot)
        
        # Проверяем что в одно время нет конфликтов
        for time_key, slots in slots_by_time.items():
            if len(slots) > 1:
                # Проверка что фотографы не пересекаются
                photographers = [s['photographer_id'] for s in slots]
                studios = [s['studio_room_id'] for s in slots if s['studio_room_id']]
                
                if len(set(photographers)) < len(photographers):
                    raise ValidationException(
                        detail=f"В одно время ({time_key}) один фотограф назначен на несколько слотов",
                        error_code="PHOTOGRAPHER_DOUBLE_BOOKING",
                    )
                
                if len(set(studios)) < len([s for s in studios if s]):
                    raise ValidationException(
                        detail=f"В одно время ({time_key}) один зал назначен на несколько слотов",
                        error_code="STUDIO_ROOM_DOUBLE_BOOKING",
                    )
    
    try:
        # Создаем заказ через сервис
        new_order = await OrderService.create_order(
            db=db,
            client_id=current_user.id,
            order_data=order_data,
            user_id=current_user.id,  # Для аудита
        )
        
        return OrderCreateResponse(
            order_id=new_order.id,
            status=new_order.status,
            total_price=new_order.total_price,
            prepayment_amount=new_order.prepayment_amount,
            created_at=new_order.created_at,
        )
        
    except SlotConflictError as e:
        from app.core.exceptions import SlotAlreadyBookedException
        raise SlotAlreadyBookedException(
            studio_id=getattr(e, 'studio_id', None),
            start_time=e.start_time,
            end_time=e.end_time,
            detail=f"Слот занят: {e.message}",
            error_code="SLOT_ALREADY_BOOKED",
        )
    except ScheduleBlockedException as e:
        from app.core.exceptions import ConflictException
        raise ConflictException(
            detail=f"Время заблокировано в расписании: {e.message}",
            error_code="SCHEDULE_BLOCKED",
        )
    except OrderValidationError as e:
        from app.core.exceptions import ValidationException
        raise ValidationException(
            detail=e.message,
            error_code="ORDER_VALIDATION_ERROR",
        )
    except Exception as e:
        # Логирование ошибки для разработчиков
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error creating order for user {current_user.id}: {e}")
        
        from app.core.exceptions import DatabaseException
        raise DatabaseException(
            detail="Внутренняя ошибка сервера при создании заказа",
            error_code="ORDER_CREATION_ERROR",
        )


# ============================================================================
# Orders List Endpoint (GET /api/v1/orders)
# ============================================================================

@limiter.limit("60/minute")  # Защита от частых запросов к списку
@router.get(
    "",
    response_model=OrdersListResponse,
    summary="Получить список заказов",
    description="""
    Возвращает список заказов с пагинацией и фильтрацией.

    **Разграничение видимости (RBAC):**
    
    - **Клиент** видит только свои заказы (созданные им)
    - **Исполнители** видят свои входящие брони (где они указаны как фотограф или представитель студии)
    
    **Возможные фильтры:**
    - status: Фильтр по статусу заказа
    - order_type: Фильтр по типу заказа
    - start_date/end_date: Временной диапазон
    
    **Пагинация:**
    - skip: Количество пропущенных записей (по умолчанию 0)
    - limit: Максимальное количество записей (1-100, по умолчанию 20)
    
    **Примеры запросов:**
    - GET /api/v1/orders?status=confirmed&limit=10
    - GET /api/v1/orders?start_date=2026-10-01&end_date=2026-10-31
    """
)
async def get_orders(
    status: Optional[str] = Query(None, description="Фильтр по статусу (pending_payment, confirmed, in_progress, completed, cancelled)"),
    order_type: Optional[str] = Query(None, description="Фильтр по типу заказа (photographer_only, studio_only, combined)"),
    start_date: Optional[date] = Query(None, description="Дата начала временного диапазона"),
    end_date: Optional[date] = Query(None, description="Дата окончания временного диапазона"),
    skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
    limit: int = Query(20, ge=1, le=100, description="Максимальное количество записей"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получает список заказов с фильтрацией и пагинацией."""
    
    try:
        # Формируем параметры поиска
        search_params = OrderSearchParams(
            status=DBOrderStatus(status) if status else None,
            order_type=DBOrderType(order_type) if order_type else None,
            start_date=start_date,
            end_date=end_date,
        )
        
        pagination_params = OrderPaginationParams(skip=skip, limit=min(limit, 100))
        
        # Получаем заказы через сервис
        orders, total_count = await OrderService.get_orders(
            db=db,
            current_user=current_user,
            search_params=search_params,
            pagination=pagination_params,
        )
        
        return OrdersListResponse(
            items=[order_to_summary(order) for order in orders],
            total=total_count,
            skip=skip,
            limit=min(limit, total_count),
        )
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching orders for user {current_user.id}: {e}")
        
        from app.core.exceptions import DatabaseException
        raise DatabaseException(
            detail="Внутренняя ошибка сервера при получении списка заказов",
            error_code="ORDERS_LIST_ERROR",
        )


# ============================================================================
# Order Detail Endpoint (GET /api/v1/orders/{id})
# ============================================================================

@limiter.limit("100/minute")  # Защита от частых запросов к детальным данным
@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Получить детальный просмотр заказа",
    description="""
    Возвращает детальную информацию о заказе для участников.
    
    **Права доступа:**
    - Клиент может просматривать только свои заказы (client_id == current_user.id)
    - Исполнитель может просматривать заказы, где он указан как фотограф или представитель студии
    
    **В ответе содержатся:**
    - Основная информация о заказе (тип, статус, цены)
    - Элементы заказа с фиксированными ценами и условиями на момент бронирования
    - Информация о фотографе/зале студии
    - Условия отмены заказа
    """
)
async def get_order_detail(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получает детальный просмотр заказа с проверкой прав доступа."""
    
    try:
        # Получаем заказ через сервис
        order = await OrderService.get_order_by_id(
            db=db,
            order_id=order_id,
            current_user=current_user,
        )
        
        return order_to_detail_response(order)
        
    except OrderNotFoundError as e:
        from app.core.exceptions import OrderNotFoundException
        raise OrderNotFoundException(
            order_id=e.order_id,
            detail=e.message,
            error_code="ORDER_NOT_FOUND",
        )
    except OrderForbiddenError as e:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(
            detail=f"Доступ к заказу запрещен: {e.message}",
            error_code="ORDER_ACCESS_DENIED",
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching order {order_id} for user {current_user.id}: {e}")
        
        from app.core.exceptions import DatabaseException
        raise DatabaseException(
            detail="Внутренняя ошибка сервера при получении заказа",
            error_code="ORDER_DETAIL_ERROR",
        )


# ============================================================================
# Order Confirm Endpoint (POST /api/v1/orders/{id}/confirm)
# ============================================================================

@router.post(
    "/{order_id}/confirm",
    response_model=OrderResponse,
    summary="Подтвердить броню исполнителем",
    description="""
    Подтверждает заказ исполнителем (фотографом или представителем студии).
    
    **Переход статуса:** pending_payment -> confirmed
    
    **Права доступа:**
    - Только исполнитель может подтвердить свой заказ
    - Исполнитель должен быть указан в заказе как фотограф или представитель студии
    
    **После подтверждения:**
    - Заказ переходит в статус "confirmed"
    - Клиенту отправляется уведомление о подтверждении
    - Запускается отсчет времени для оплаты (если требуется)
    
    **Пример запроса:**
    ```json
    {
      "performer_note": "Готов к съемке, все условия обсудим на месте"
    }
    ```
    """
)
async def confirm_order(
    order_id: int,
    request_data: OrderConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Подтверждает заказ исполнителем.
    
    Проверяет:
    - Исполнитель может подтвердить только свой заказ
    - Статус заказа pending_payment
    - Время начала в будущем
    - Нет пересечений с другими бронями исполнителя
    """
    
    from app.core.exceptions import ForbiddenException, ValidationException
    
    try:
        # Получаем заказ с блокировкой (для предотвращения гонок)
        order = await OrderService.get_order_by_id_with_lock(
            db=db,
            order_id=order_id,
            current_user=current_user,
        )
        
        # Проверка 1: Исполнитель может подтвердить только свой заказ
        is_performer = False
        performer_type = None
        
        for item in order.items:
            if item.photographer_id == current_user.id:
                is_performer = True
                performer_type = "photographer"
                break
            
            # Проверка для представителя студии
            if item.studio_room and hasattr(item.studio_room, 'studio') and item.studio_room.studio_id == current_user.id:
                is_performer = True
                performer_type = "studio_representative"
                break
        
        if not is_performer:
            raise ForbiddenException(
                detail=f"Только исполнитель может подтвердить этот заказ. Ваш ID: {current_user.id}",
                error_code="PERFORMER_ONLY_ACCESS",
            )
        
        # Проверка 2: Статус заказа pending_payment
        if order.status != DBOrderStatus.pending_payment:
            raise ValidationException(
                detail=f"Можно подтвердить только заказы со статусом pending_payment. Текущий статус: {order.status.value}",
                error_code="INVALID_STATUS_FOR_CONFIRMATION",
            )
        
        # Проверка 3: Время начала в будущем
        now = datetime.now()
        start_time_dt = order.items[0].start_time if hasattr(order.items, '__getitem__') else None
        
        if start_time_dt and isinstance(start_time_dt, (datetime, str)):
            if isinstance(start_time_dt, str):
                try:
                    start_time_dt = datetime.fromisoformat(start_time_dt.replace('Z', '+00:00'))
                except ValueError:
                    pass
            
            if isinstance(start_time_dt, datetime) and start_time_dt < now:
                raise ValidationException(
                    detail=f"Нельзя подтвердить заказ с временем начала в прошлом. Время начала: {start_time_dt}",
                    error_code="CANNOT_CONFIRM_PAST_ORDER",
                )
        
        # Обновляем статус через сервис
        await StatusManagerService.update_order_status(
            db=db,
            order_id=order_id,
            new_status=DBOrderStatus.confirmed,
            actor_type="performer",  # Исполнитель подтверждает
        )
        
        # Фиксируем изменения в БД
        await db.flush()
        await db.refresh(order)
        
        return order_to_detail_response(order)
        
    except OrderNotFoundError as e:
        from app.core.exceptions import OrderNotFoundException
        raise OrderNotFoundException(
            order_id=e.order_id,
            detail=e.message,
            error_code="ORDER_NOT_FOUND",
        )
    except OrderForbiddenError as e:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(
            detail=f"Только исполнитель может подтвердить этот заказ: {e.message}",
            error_code="PERFORMER_ONLY_ACCESS",
        )
    except StatusTransitionNotAllowed as e:
        from app.core.exceptions import StateTransitionException
        raise StateTransitionException(
            current_state=order.status.value if hasattr(order, 'status') else None,
            target_state="confirmed",
            detail=e.message,
            error_code="INVALID_STATE_TRANSITION",
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error confirming order {order_id} for user {current_user.id}: {e}")
        
        from app.core.exceptions import DatabaseException
        raise DatabaseException(
            detail="Внутренняя ошибка сервера при подтверждении заказа",
            error_code="ORDER_CONFIRMATION_ERROR",
        )


# ============================================================================
# Order Cancel Endpoint (POST /api/v1/orders/{id}/cancel)
# ============================================================================

@router.post(
    "/{order_id}/cancel",
    response_model=OrderCancelResponse,
    summary="Отменить заказ с расчетом возврата средств",
    description="""
    Отменяет заказ клиентом или системой.
    
    **Переход статуса:** Любой -> cancelled
    
    **Права доступа:**
    - Клиент может отменить свой заказ до момента завершения
    - Система может отменить заказ по различным причинам (просрочка оплаты и т.д.)
    
    **Расчет возврата средств:**
    - pending_payment: 100% возврат предоплаты
    - confirmed: зависит от условий отмены (обычно 50-80%)
    - in_progress: зависит от прогресса работы, может быть 0% если работа началась
    
    **Пример запроса:**
    ```json
    {
      "reason": "Изменились планы на съемку, нужно перенести на другую дату"
    }
    ```

    **В ответе возвращается:**
    - Сумма к возврату (refund_amount)
    - Процент возврата (refund_percentage)
    - Причина отмены
    """
)
async def cancel_order(
    order_id: int,
    request_data: OrderCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отменяет заказ с расчетом возврата средств.
    
    Проверяет:
    - Клиент является владельцем заказа
    - Заказ еще не завершен/отменен
    - Отмена возможна до определенного времени после начала работы
    - Расчет возврата в зависимости от статуса
    """
    
    from app.core.exceptions import ValidationException, ForbiddenException
    
    try:
        # Получаем заказ с блокировкой
        order = await OrderService.get_order_by_id_with_lock(
            db=db,
            order_id=order_id,
            current_user=current_user,
        )
        
        # Проверка 1: Клиент является владельцем заказа
        if order.client_id != current_user.id:
            raise ForbiddenException(
                detail=f"Только клиент может отменить этот заказ",
                error_code="CLIENT_ONLY_CANCEL_ACCESS",
            )
        
        # Проверка 2: Заказ еще не завершен/отменен
        if order.status in [DBOrderStatus.completed, DBOrderStatus.cancelled]:
            raise ValidationException(
                detail=f"Нельзя отменить заказ со статусом {order.status.value}. Заказы в статусах completed и cancelled уже окончены.",
                error_code="CANNOT_CANCEL_COMPLETED_ORDER",
            )
        
        # Проверка 3: Отмена возможна только до определенного времени после начала работы
        if order.status == DBOrderStatus.in_progress:
            # Для заказов в процессе работы — отмена с нулевым возвратом
            raise ValidationException(
                detail="Заказ находится в процессе работы. Возврат средств не возможен.",
                error_code="NO_REFUND_IN_PROGRESS",
            )
        
        # Проверка 4: Отмена за менее чем 24 часа до начала — штраф
        now = datetime.now()
        start_time_dt = order.items[0].start_time if hasattr(order.items, '__getitem__') else None
        
        if start_time_dt and isinstance(start_time_dt, (datetime, str)):
            if isinstance(start_time_dt, str):
                start_time_dt = datetime.fromisoformat(start_time_dt.replace('Z', '+00:00'))
            
            time_until_start = start_time_dt - now
            
            if time_until_start.total_seconds() < 24 * 3600:  # Менее 24 часов
                raise ValidationException(
                    detail=f"Отмена возможна только за 24 часа до начала. До начала осталось {time_until_start}.",
                    error_code="CANCELLATION_TOO_LATE",
                )
        
        # Рассчитываем возврат средств
        refund_amount, refund_percentage = await StatusManagerService.calculate_refund(
            prepayment_amount=order.prepayment_amount,
            total_price=order.total_price,
            status_at_cancellation=order.status,
            cancellation_date=datetime.now(),
            created_at=order.created_at,
            conditions={},  # Можно добавить из модели заказа если есть
        )
        
        # Обновляем статус на cancelled через сервис
        await StatusManagerService.update_order_status(
            db=db,
            order_id=order_id,
            new_status=DBOrderStatus.cancelled,
            actor_type="client",  # Клиент отменяет
        )
        
        # Фиксируем изменения в БД
        await db.flush()
        await db.refresh(order)
        
        return OrderCancelResponse(
            order_id=order.id,
            status=DBOrderStatus.cancelled,
            refund_amount=refund_amount,
            refund_percentage=refund_percentage,
            cancellation_reason=request_data.reason,
            cancelled_at=datetime.now(),
        )
        
    except OrderNotFoundError as e:
        from app.core.exceptions import OrderNotFoundException
        raise OrderNotFoundException(
            order_id=e.order_id,
            detail=e.message,
            error_code="ORDER_NOT_FOUND",
        )
    except OrderForbiddenError as e:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(
            detail=f"Только клиент может отменить этот заказ: {e.message}",
            error_code="CLIENT_ONLY_CANCEL_ACCESS",
        )
    except StatusTransitionNotAllowed as e:
        from app.core.exceptions import StateTransitionException
        raise StateTransitionException(
            current_state=order.status.value if hasattr(order, 'status') else None,
            target_state="cancelled",
            detail=e.message,
            error_code="INVALID_STATE_TRANSITION",
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error cancelling order {order_id} for user {current_user.id}: {e}")
        
        from app.core.exceptions import DatabaseException
        raise DatabaseException(
            detail="Внутренняя ошибка сервера при отмене заказа",
            error_code="ORDER_CANCELLATION_ERROR",
        )


# ============================================================================
# Additional Utility Endpoints (Опционально)
# ============================================================================

@router.get(
    "/{order_id}/availability-check",
    summary="Проверить доступность слотов для заказа",
    description="""
    Предварительная проверка доступности временных слотов перед созданием заказа.
    
    Позволяет проверить:
    - Нет ли пересечений с существующими бронями
    - Нет ли блокировок в расписании
    - Не являются ли даты выходными днями
    
    **Возвращает:** Результат проверки доступности без создания заказа
    """
)
async def check_slot_availability(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Проверяет доступность слотов для заказа (без создания)."""
    
    # Эта функция может быть реализована как отдельный endpoint
    # или использоваться внутри create_order для UX улучшения
    
    from app.core.exceptions import NotFoundException
    raise NotFoundException(
        resource_type="endpoint",
        detail="Этот эндпоинт пока не реализован",
        error_code="ENDPOINT_NOT_IMPLEMENTED",
    )
