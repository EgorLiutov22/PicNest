"""
Сервис проверки доступности ресурсов.

Использует паттерн Strategy: словарь чекеров, ключ — resource_type.
Новый тип ресурса добавляется одной строкой в AVAILABILITY_CHECKERS.
"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.orderitem import OrderItem
from app.models.orderstatus import OrderStatus


# Статусы, при которых заказ реально занимает ресурс.
# Неоплаченные (pending_payment) и отменённые слот не держат.
BLOCKING_STATUSES = (
    OrderStatus.confirmed,
    OrderStatus.in_progress,
    OrderStatus.completed,
)


async def _find_conflict(
    db: AsyncSession,
    resource_type: str,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_order_id: Optional[int] = None,
) -> Optional[int]:
    """Ищет пересечение с существующей позицией того же ресурса.

    Пересечение интервалов: new_start < existing_end AND new_end > existing_start.
    Возвращает id конфликтующей позиции или None.
    """
    query = (
        select(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            and_(
                OrderItem.resource_type == resource_type,
                OrderItem.resource_id == resource_id,
                Order.status.in_(BLOCKING_STATUSES),
                OrderItem.start_time < end_time,
                OrderItem.end_time > start_time,
            )
        )
        .limit(1)
    )
    if exclude_order_id:
        query = query.where(Order.id != exclude_order_id)

    result = await db.execute(query)
    # first(), а не scalar_one_or_none(): при нескольких конфликтах
    # последний бросил бы MultipleResultsFound.
    return result.scalars().first()


async def check_photographer_availability(
    db: AsyncSession,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_order_id: Optional[int] = None,
) -> None:
    """Проверяет, что фотограф свободен в указанный интервал."""
    conflict = await _find_conflict(
        db, "photographer", resource_id, start_time, end_time, exclude_order_id
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Фотограф (id={resource_id}) уже забронирован на это время",
        )


async def check_studio_room_availability(
    db: AsyncSession,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_order_id: Optional[int] = None,
) -> None:
    """Проверяет, что зал студии свободен в указанный интервал."""
    conflict = await _find_conflict(
        db, "studio_room", resource_id, start_time, end_time, exclude_order_id
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Зал студии (id={resource_id}) уже забронирован на это время",
        )


# === Диспетчер ===
AVAILABILITY_CHECKERS = {
    "photographer": check_photographer_availability,
    "studio_room": check_studio_room_availability,
    # Новые типы добавляются сюда одной строкой:
    # "makeup_artist": check_makeup_artist_availability,
}


async def validate_items_availability(
    db: AsyncSession,
    items: List[Any],
    exclude_order_id: Optional[int] = None,
) -> None:
    """
    Проверяет доступность всех элементов заказа.

    items — список объектов с полями:
      resource_type, resource_id, start_time, end_time

    Кидает HTTPException(409) при первом найденном конфликте.
    Кидает HTTPException(400) при неизвестном resource_type.
    """
    for item in items:
        checker = AVAILABILITY_CHECKERS.get(item.resource_type)
        if not checker:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неизвестный тип ресурса: {item.resource_type}",
            )
        await checker(
            db=db,
            resource_id=item.resource_id,
            start_time=item.start_time,
            end_time=item.end_time,
            exclude_order_id=exclude_order_id,
        )
