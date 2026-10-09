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

from datetime import date, datetime
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
    """Создает новый заказ с валидацией и снапшотом данных."""
    
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
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "slot_conflict",
                "message": e.message,
                "conflicting_order_id": getattr(e, 'conflicting_order_id', None),
            },
        )
    except ScheduleBlockedException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "schedule_blocked",
                "message": e.message,
                "blocked_by": getattr(e, 'blocked_by', None),
            },
        )
    except OrderValidationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "validation_error",
                "message": e.message,
            },
        )
    except Exception as e:
        # Логирование ошибки для разработчиков
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error creating order for user {current_user.id}: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при создании заказа",
        )


# ============================================================================
# Orders List Endpoint (GET /api/v1/orders)
# ============================================================================

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
        
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при получении списка заказов",
        )


# ============================================================================
# Order Detail Endpoint (GET /api/v1/orders/{id})
# ============================================================================

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
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "not_found",
                "message": e.message,
                "order_id": e.order_id,
            },
        )
    except OrderForbiddenError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "forbidden",
                "message": e.message,
                "order_id": getattr(e, 'order_id', None),
            },
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching order {order_id} for user {current_user.id}: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при получении заказа",
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
    """Подтверждает заказ исполнителем."""
    
    try:
        # Получаем заказ с блокировкой (для предотвращения гонок)
        order = await OrderService.get_order_by_id_with_lock(
            db=db,
            order_id=order_id,
            current_user=current_user,
        )
        
        # Проверяем что исполнитель может подтвердить этот заказ
        is_performer = False
        
        for item in order.items:
            if item.photographer_id == current_user.id:
                is_performer = True
                break
            
            # Проверка для представителя студии (упрощенная)
            if item.studio_room and item.studio_room.studio_id == current_user.id:
                is_performer = True
                break
        
        if not is_performer:
            raise OrderForbiddenError(
                f"Только исполнитель может подтвердить этот заказ",
                order_id=order_id,
            )
        
        # Проверяем текущий статус
        if order.status != DBOrderStatus.pending_payment:
            raise StatusTransitionNotAllowed(
                f"Можно подтвердить только заказы со статусом pending_payment"
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
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "not_found",
                "message": e.message,
                "order_id": e.order_id,
            },
        )
    except OrderForbiddenError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "forbidden",
                "message": e.message,
                "order_id": getattr(e, 'order_id', None),
            },
        )
    except StatusTransitionNotAllowed as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "invalid_transition",
                "message": e.message,
            },
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error confirming order {order_id} for user {current_user.id}: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при подтверждении заказа",
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
    """Отменяет заказ с расчетом возврата средств."""
    
    try:
        # Получаем заказ с блокировкой
        order = await OrderService.get_order_by_id_with_lock(
            db=db,
            order_id=order_id,
            current_user=current_user,
        )
        
        # Проверяем права клиента на отмену
        if order.client_id != current_user.id:
            raise OrderForbiddenError(
                f"Только клиент может отменить этот заказ",
                order_id=order_id,
            )
        
        # Проверяем что заказ еще не завершен/отменен
        if order.status in [DBOrderStatus.completed, DBOrderStatus.cancelled]:
            raise StatusTransitionNotAllowed(
                f"Нельзя отменить заказ со статусом {order.status.value}"
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
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "not_found",
                "message": e.message,
                "order_id": e.order_id,
            },
        )
    except OrderForbiddenError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "forbidden",
                "message": e.message,
                "order_id": getattr(e, 'order_id', None),
            },
        )
    except StatusTransitionNotAllowed as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error_type": "invalid_transition",
                "message": e.message,
            },
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error cancelling order {order_id} for user {current_user.id}: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при отмене заказа",
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
    
    raise HTTPException(
        status_code=501,
        detail="Этот эндпоинт пока не реализован",
    )
