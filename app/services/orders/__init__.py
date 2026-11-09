"""
Сервисы для модуля заказов PicNest.

Этот модуль содержит бизнес-логику для:
- Создания заказа с захватом слотов и снапшотом данных
- Управления статусами заказов (подтверждение, отмена)
- Расчета возврата средств при отмене

Учёт занятости ресурсов — в app.services.schedule.occupancy.
"""

from .services import (
    # Сервисы
    OrderService,
    StatusManagerService,

    # Исключения
    OrderValidationError,
    SlotConflictError,
    ScheduleBlockedException,
    StatusTransitionNotAllowed,
    OrderNotFoundError,
    OrderForbiddenError,
)
from app.services.schedule.occupancy import SlotTakenError

__all__ = [
    "OrderService",
    "StatusManagerService",
    "OrderValidationError",
    "SlotConflictError",
    "ScheduleBlockedException",
    "StatusTransitionNotAllowed",
    "OrderNotFoundError",
    "OrderForbiddenError",
    "SlotTakenError",
]
