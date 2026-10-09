from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from typing import Optional

from app.core.database import get_db

router = APIRouter(prefix="/schedules", tags=["Schedules & Availability"])

@router.get("/available")
async def get_available_slots(
    target_date: date = Query(..., description="Дата в формате YYYY-MM-DD"),
    room_id: Optional[int] = Query(None, description="ID зала студии"),
    photographer_id: Optional[int] = Query(None, description="ID фотографа"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список свободных таймслотов на дату.
    Учитывает шаблоны расписания, исключения (выходные) и уже забронированные часы.
    """
    if not room_id and not photographer_id:
        return {"error": "Необходимо указать либо room_id, либо photographer_id"}

    # Бизнес-логика бэкенда:
    # 1. Проверить таблицу schedule_exceptions (выходной ли день?)
    # 2. Взять шаблон из schedule_templates для данного дня недели (day_of_week)
    # 3. Найти все занятые order_items за этот день и вычесть их из рабочего интервала
    
    # Заглушка ответа со свободными слотами:
    return {
        "date": target_date,
        "resource_type": "room" if room_id else "photographer",
        "resource_id": room_id or photographer_id,
        "available_slots": [
            {"start": "10:00", "end": "12:00"},
            {"start": "13:00", "end": "16:00"},
            {"start": "18:00", "end": "20:00"}
        ]
    }