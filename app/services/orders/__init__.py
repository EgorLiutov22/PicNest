"""
Сервисы для модуля заказов PicNest.

Этот модуль содержит бизнес-логику для:
- Создания заказа с валидацией слотов и снапшотом данных
- Проверки доступности временных интервалов (фотограф/зал)
- Управления статусами заказов (подтверждение, отмена)
- Расчета возврата средств при отмене

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

from .services import (
    # Сервисы
    OrderService,
    AvailabilityCheckerService,
    StatusManagerService,
    
    # Исключения
    OrderValidationError,
    SlotConflictError,
    ScheduleBlockedException,
    StatusTransitionNotAllowed,
    OrderNotFoundError,
    OrderForbiddenError,
)

__all__ = [
    "OrderService",
    "AvailabilityCheckerService",
    "StatusManagerService",
    "OrderValidationError",
    "SlotConflictError",
    "ScheduleBlockedException",
    "StatusTransitionNotAllowed",
    "OrderNotFoundError",
    "OrderForbiddenError",
]
