from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.order import OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user) # Заглушка авторизации
):
    """
    Создание нового заказа (одиночный или комбинированный).
    Фиксирует цены и условия на момент брони.
    """
    # Условный client_id (в реальном проекте берется из current_user.id)
    client_id = 1 
    
    total_price = 0.0
    items_to_create = []

    # Расчет стоимости и подготовка позиций
    for item in order_in.items:
        # Здесь должна быть логика проверки занятости слота (Race Condition check)
        # и получения актуальной цены из базы (photographer_services или studio_rooms).
        
        # Для примера фиксируем тестовую цену:
        fixed_price = 1500.0 
        total_price += fixed_price

        items_to_create.append(
            OrderItem(
                photographer_id=item.photographer_id,
                photographer_service_id=item.photographer_service_id,
                studio_room_id=item.studio_room_id,
                start_time=item.start_time,
                end_time=item.end_time,
                fixed_price=fixed_price,
                fixed_conditions={"cancellation_policy": "standard_24h"}
            )
        )

    prepayment_amount = total_price * 0.3  # Предоплата 30%

    new_order = Order(
        client_id=client_id,
        order_type=order_in.order_type,
        total_price=total_price,
        prepayment_amount=prepayment_amount,
        status="pending_payment"
    )
    
    db.add(new_order)
    await db.flush() # Получаем ID заказа до коммита

    for item_obj in items_to_create:
        item_obj.order_id = new_order.id
        db.add(item_obj)

    await db.commit()
    await db.refresh(new_order)
    return new_order


@router.get("/", response_model=List[OrderResponse])
async def get_my_orders(
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user)
):
    """Получить список заказов текущего пользователя."""
    client_id = 1
    result = await db.execute(select(Order).where(Order.client_id == client_id))
    orders = result.scalars().all()
    return orders