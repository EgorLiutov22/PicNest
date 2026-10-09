"""
Pydantic v2 схемы для модуля заказов PicNest Marketplace.

Этот модуль содержит все модели данных для работы с заказами:
- Валидация входных данных при создании заказа (POST /api/v1/orders)
- Формирование ответов API с детальной информацией о заказе
- Параметры поиска и пагинации для списка заказов
- Запросы на подтверждение и отмену заказа

Поддерживает три типа бронирования:
  * photographer_only - только фотограф
  * studio_only - только зал фотостудии  
  * combined - комбинированный заказ (фотограф + зал)

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

from __future__ import annotations

from datetime import datetime, date, time
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr
from typing_extensions import Annotated


# ============================================================================
# Enums and Type Aliases
# ============================================================================

class OrderTypeEnum(str, PyEnum):
    """Тип заказа (бронирования)."""
    
    photographer_only = "photographer_only"  # Только фотограф
    studio_only = "studio_only"  # Только зал студии
    combined = "combined"  # Комбинированный заказ


class OrderStatusEnum(str, PyEnum):
    """Статус заказа и правила перехода между состояниями."""
    
    pending_payment = "pending_payment"  # Ожидает оплаты
    confirmed = "confirmed"  # Подтвержден исполнителем
    in_progress = "in_progress"  # Выполняется
    completed = "completed"  # Завершен
    cancelled = "cancelled"  # Отменен
    disputed = "disputed"  # В споре


class OrderStatusTransitionRule(BaseModel):
    """Правило перехода между статусами заказа."""
    
    from_status: List[OrderStatusEnum] = Field(
        ...,
        description="Список статусов, из которых возможен переход"
    )
    to_status: OrderStatusEnum = Field(
        ...,
        description="Целевой статус"
    )
    allowed_by: Literal["client", "performer", "system"] = Field(
        ...,
        description="Кто может инициировать этот переход (клиент, исполнитель или система)"
    )


# Правила переходов между статусами
ORDER_STATUS_TRANSITIONS: List[OrderStatusTransitionRule] = [
    OrderStatusTransitionRule(
        from_status=[OrderStatusEnum.pending_payment],
        to_status=OrderStatusEnum.confirmed,
        allowed_by="performer"
    ),
    OrderStatusTransitionRule(
        from_status=[OrderStatusEnum.confirmed],
        to_status=OrderStatusEnum.in_progress,
        allowed_by="system"
    ),
    OrderStatusTransitionRule(
        from_status=[OrderStatusEnum.in_progress],
        to_status=OrderStatusEnum.completed,
        allowed_by="system"
    ),
    OrderStatusTransitionRule(
        from_status=[
            OrderStatusEnum.pending_payment,
            OrderStatusEnum.confirmed,
            OrderStatusEnum.in_progress
        ],
        to_status=OrderStatusEnum.cancelled,
        allowed_by="client"
    ),
    OrderStatusTransitionRule(
        from_status=[
            OrderStatusEnum.pending_payment,
            OrderStatusEnum.confirmed,
            OrderStatusEnum.in_progress,
            OrderStatusEnum.completed
        ],
        to_status=OrderStatusEnum.cancelled,
        allowed_by="system"
    ),
]


# ============================================================================
# Base Schema
# ============================================================================

class OrderBase(BaseModel):
    """Базовая модель заказа без обязательных полей."""
    
    order_type: OrderTypeEnum = Field(
        ...,
        description="Тип бронирования",
        examples=["photographer_only"]
    )


# ============================================================================
# Order Item Schemas (для создания заказа)
# ============================================================================

class OrderItemCreate(BaseModel):
    """Схема для создания элемента заказа.
    
    Каждый элемент заказа представляет собой бронирование конкретного
    ресурса (фотографа или зала студии) на определенный временной интервал.
    """
    
    photographer_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID фотографа (обязательно для photographer_only и combined)"
    )
    
    photographer_service_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID услуги фотографа (для photographer_only и combined)"
    )
    
    studio_room_id: Optional[int] = Field(
        None,
        ge=1,
        description="ID зала студии (обязательно для studio_only и combined)"
    )
    
    start_time: datetime = Field(
        ...,
        description="Время начала бронирования",
        examples=["2026-10-15T10:00:00+03:00"]
    )
    
    end_time: datetime = Field(
        ...,
        description="Время окончания бронирования",
        examples=["2026-10-15T14:00:00+03:00"]
    )
    
    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_datetime_timezone(cls, v: datetime) -> datetime:
        """Проверяет что датама имеет timezone."""
        if v.tzinfo is None:
            raise ValueError('datetime должен содержать timezone')
        return v
    
    @model_validator(mode='after')
    def validate_time_range(self) -> 'OrderItemCreate':
        """Валидирует временной интервал."""
        if self.end_time <= self.start_time:
            raise ValueError('end_time должно быть строго больше start_time')
        
        # Проверка длительности (минимум 1 час для фотографа, минимум min_rent_hours для зала)
        duration_minutes = (self.end_time - self.start_time).total_seconds() / 60
        
        if self.photographer_id:
            if duration_minutes < 60:
                raise ValueError('Минимальная длительность бронирования фотографа — 1 час')
        
        return self
    
    @model_validator(mode='after')
    def validate_item_owner(self) -> 'OrderItemCreate':
        """Проверяет что указан именно один из владельцев (фотограф или зал)."""
        has_photographer = self.photographer_id is not None
        has_studio_room = self.studio_room_id is not None
        
        if not has_photographer and not has_studio_room:
            raise ValueError('Должен быть указан фотограф или зал студии')
        
        if has_photographer and has_studio_room:
            # Для combined типа оба должны быть указаны - это проверяется в основном заказe
            pass
        
        return self


# ============================================================================
# Order Creation Schemas
# ============================================================================

class OrderCreate(BaseModel):
    """Схема для создания нового заказа клиентом.
    
    Содержит все необходимые данные для бронирования:
    - Тип заказа (фотограф/зал/комбинированный)
    - Элементы заказа с временными интервалами и ценами
    - Условия отмены и предоплата
    
    Важно: Цены и условия должны быть указаны явно, так как они будут
    зафиксированы на момент создания заказа (снапшот).
    """
    
    order_type: OrderTypeEnum = Field(
        ...,
        description="Тип бронирования",
        examples=["photographer_only"]
    )
    
    items: List[OrderItemCreate] = Field(
        ...,
        min_items=1,
        max_items=2,  # Максимум 2 элемента (фотограф + зал для combined)
        description="Элементы заказа (бронирования ресурсов)"
    )
    
    prepayment_amount: Decimal = Field(
        ...,
        ge=Decimal('0.00'),
        le=Decimal('1000000.00'),
        description="Сумма предоплаты",
        examples=[Decimal("5000.00")]
    )
    
    cancellation_conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Условия отмены заказа (снапшот на момент бронирования)"
    )
    
    @field_validator('prepayment_amount')
    @classmethod
    def validate_prepayment(cls, v: Decimal) -> Decimal:
        """Валидация суммы предоплаты."""
        if v < 0:
            raise ValueError('Предоплата не может быть отрицательной')
        return v
    
    @model_validator(mode='after')
    def validate_order_type_consistency(self) -> 'OrderCreate':
        """Проверяет соответствие типа заказа элементам."""
        has_photographer = any(item.photographer_id is not None for item in self.items)
        has_studio_room = any(item.studio_room_id is not None for item in self.items)
        
        if self.order_type == OrderTypeEnum.photographer_only:
            if not has_photographer or has_studio_room:
                raise ValueError(
                    'Для типа photographer_only должен быть указан только фотограф'
                )
        
        elif self.order_type == OrderTypeEnum.studio_only:
            if not has_studio_room or has_photographer:
                raise ValueError(
                    'Для типа studio_only должен быть указан только зал студии'
                )
        
        elif self.order_type == OrderTypeEnum.combined:
            if not (has_photographer and has_studio_room):
                raise ValueError(
                    'Для типа combined должны быть указаны и фотограф и зал студии'
                )
        
        return self
    
    @model_validator(mode='after')
    def validate_all_items_same_datetime_range(self) -> 'OrderCreate':
        """Проверяет что все элементы заказа в одном временном интервале."""
        if len(self.items) > 1:
            start_times = [item.start_time for item in self.items]
            end_times = [item.end_time for item in self.items]
            
            # Все start и end должны совпадать для combined типа
            if len(set(str(t) for t in start_times)) != 1 or \
               len(set(str(t) for t in end_times)) != 1:
                raise ValueError(
                    'Все элементы заказа должны иметь одинаковые время начала и окончания'
                )
        
        return self


class OrderCreateResponse(BaseModel):
    """Ответ на успешное создание заказа."""
    
    order_id: int = Field(..., description="ID созданного заказа")
    status: OrderStatusEnum = Field(..., description="Статус заказа")
    total_price: Decimal = Field(..., description="Общая стоимость заказа")
    prepayment_amount: Decimal = Field(..., description="Сумма предоплаты")
    created_at: datetime = Field(..., description="Время создания заказа")
    
    class Config:
        from_attributes = True


# ============================================================================
# Order Item Response Schemas (для чтения)
# ============================================================================

class PhotographerInfo(BaseModel):
    """Информация о фотографе в заказе."""
    
    id: int = Field(..., description="ID фотографа")
    display_name: str = Field(..., description="Имя для отображения")
    service_title: Optional[str] = Field(None, description="Название услуги")
    fixed_price: Decimal = Field(..., description="Фиксированная цена на момент бронирования")


class StudioRoomInfo(BaseModel):
    """Информация о зале студии в заказе."""
    
    id: int = Field(..., description="ID зала")
    name: str = Field(..., description="Название зала")
    studio_title: str = Field(..., description="Название студии")
    address: str = Field(..., description="Адрес студии")
    fixed_price: Decimal = Field(..., description="Фиксированная цена на момент бронирования")


class OrderItemResponse(BaseModel):
    """Детальная информация об элементе заказа (бронировании)."""
    
    id: int = Field(..., description="ID элемента заказа")
    photographer_id: Optional[int] = Field(None, description="ID фотографа")
    photographer_info: Optional[PhotographerInfo] = None
    
    photographer_service_id: Optional[int] = Field(None, description="ID услуги")
    
    studio_room_id: Optional[int] = Field(None, description="ID зала студии")
    studio_room_info: Optional[StudioRoomInfo] = None
    
    start_time: datetime = Field(..., description="Время начала бронирования")
    end_time: datetime = Field(..., description="Время окончания бронирования")
    fixed_price: Decimal = Field(..., description="Фиксированная цена (снапшот)")
    fixed_conditions: Dict[str, Any] = Field(
        ..., 
        description="Условия отмены на момент бронирования"
    )


# ============================================================================
# Order Response Schemas
# ============================================================================

class OrderResponse(BaseModel):
    """Детальная информация о заказе для участников."""
    
    id: int = Field(..., description="ID заказа")
    order_type: OrderTypeEnum = Field(..., description="Тип заказа")
    status: OrderStatusEnum = Field(..., description="Статус заказа")
    total_price: Decimal = Field(..., description="Общая стоимость заказа")
    prepayment_amount: Decimal = Field(..., description="Сумма предоплаты")
    created_at: datetime = Field(..., description="Время создания заказа")
    
    client_id: int = Field(..., description="ID клиента (создателя заказа)")
    
    items: List[OrderItemResponse] = Field(
        ..., 
        description="Элементы заказа"
    )
    
    cancellation_conditions: Dict[str, Any] = Field(
        ..., 
        description="Условия отмены заказа"
    )
    
    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    """Краткая информация о заказе (для списка)."""
    
    id: int = Field(..., description="ID заказа")
    order_type: OrderTypeEnum = Field(..., description="Тип заказа")
    status: OrderStatusEnum = Field(..., description="Статус заказа")
    total_price: Decimal = Field(..., description="Общая стоимость")
    created_at: datetime = Field(..., description="Время создания")
    
    class Config:
        from_attributes = True


class OrdersListResponse(BaseModel):
    """Ответ со списком заказов с пагинацией."""
    
    items: List[OrderSummary] = Field(
        ..., 
        description="Список заказов"
    )
    total: int = Field(..., description="Общее количество заказов")
    skip: int = Field(..., description="Пропущенное количество")
    limit: int = Field(..., description="Лимит записей")


# ============================================================================
# Query Parameters Schemas
# ============================================================================

class OrderSearchParams(BaseModel):
    """Параметры поиска заказов."""
    
    status: Optional[OrderStatusEnum] = Field(
        None, 
        description="Фильтр по статусу заказа"
    )
    
    order_type: Optional[OrderTypeEnum] = Field(
        None, 
        description="Фильтр по типу заказа"
    )
    
    start_date: Optional[date] = Field(
        None, 
        description="Дата начала временного диапазона"
    )
    
    end_date: Optional[date] = Field(
        None, 
        description="Дата окончания временного диапазона"
    )


class OrderPaginationParams(BaseModel):
    """Параметры пагинации для списка заказов."""
    
    skip: int = Field(
        0, 
        ge=0, 
        description="Количество пропущенных записей"
    )
    limit: int = Field(
        20, 
        ge=1, 
        le=100, 
        description="Максимальное количество записей"
    )


# ============================================================================
# Order Management Schemas
# ============================================================================

class OrderConfirmRequest(BaseModel):
    """Запрос на подтверждение заказа исполнителем."""
    
    performer_note: Optional[str] = Field(
        None, 
        max_length=500,
        description="Заметка исполнителя (опционально)"
    )
    
    @field_validator('performer_note')
    @classmethod
    def validate_note(cls, v: Optional[str]) -> Optional[str]:
        """Убирает лишние пробелы из заметки."""
        if v:
            return v.strip()
        return v


class OrderCancelRequest(BaseModel):
    """Запрос на отмену заказа клиентом.
    
    Содержит причину отмены для аналитики и расчета возврата средств.
    """
    
    reason: str = Field(
        ..., 
        min_length=10, 
        max_length=500, 
        description="Причина отмены (минимум 10 символов)"
    )
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v: str) -> str:
        """Убирает лишние пробелы из причины."""
        return v.strip()


class OrderCancelResponse(BaseModel):
    """Ответ на отмену заказа с расчетом возврата средств."""
    
    order_id: int = Field(..., description="ID отмененного заказа")
    status: OrderStatusEnum = Field(..., description="Новый статус (cancelled)")
    refund_amount: Decimal = Field(..., description="Сумма к возврату клиенту")
    refund_percentage: float = Field(..., description="Процент возврата")
    cancellation_reason: str = Field(..., description="Причина отмены")
    cancelled_at: datetime = Field(..., description="Время отмены заказа")
    
    class Config:
        from_attributes = True


# ============================================================================
# Validation Helper Schemas (для валидации слотов)
# ============================================================================

class SlotConflictErrorDetail(BaseModel):
    """Детали конфликта временных слотов."""
    
    order_item_id: Optional[int] = Field(None, description="ID элемента заказа")
    photographer_id: Optional[int] = Field(None, description="ID фотографа")
    studio_room_id: Optional[int] = Field(None, description="ID зала студии")
    start_time: datetime = Field(..., description="Время начала конфликта")
    end_time: datetime = Field(..., description="Время окончания конфликта")
    conflicting_order_id: int = Field(..., description="ID конфликтующего заказа")


class AvailabilityCheckResult(BaseModel):
    """Результат проверки доступности слотов."""
    
    is_available: bool = Field(..., description="Доступен ли слот")
    error_type: Optional[str] = Field(
        None, 
        description="Тип ошибки (conflict/block/exception)"
    )
    message: str = Field(..., description="Сообщение об ошибке или доступности")
    details: Optional[SlotConflictErrorDetail] = None
