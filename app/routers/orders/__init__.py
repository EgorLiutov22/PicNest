"""
RESTful API роутеры для модуля заказов PicNest.

Этот модуль содержит все эндпоинты для управления заказами:
- POST /api/v1/orders - создание заказа клиентом
- GET /api/v1/orders - список заказов с разграничением видимости
- GET /api/v1/orders/{id} - детальный просмотр заказа
- POST /api/v1/orders/{id}/confirm - подтверждение исполнителем
- POST /api/v1/orders/{id}/cancel - отмена клиентом

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

from .router import router

__all__ = ["router"]
