from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


from enum import Enum

class UserRole(str, Enum):
    client = "client"
    photographer = "photographer"
    studio = "studio"

class OrderType(str, Enum):
    photographer_only = "photographer_only"
    studio_only = "studio_only"
    combined = "combined"

class OrderStatus(str, Enum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    disputed = "disputed"



class UserRegister(BaseModel):
    email: EmailStr
    phone: str = Field(..., description="Номер телефона в международном формате")
    password: str = Field(..., min_string_length=6, description="Минимум 6 символов")
    role: UserRole
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = "Europe/Moscow"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    phone: str
    role: UserRole
    status: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    city: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PhotographerServiceCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    photos_count: Optional[int] = None
    delivery_days: Optional[int] = None
    price: Decimal = Field(..., ge=0)

class PhotographerProfileUpdate(BaseModel):
    display_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    legal_status: Optional[str] = None  # самозанятый, ИП и т.д.



class StudioRoomCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    area: Optional[int] = Field(None, gt=0)
    ceiling_height: Optional[Decimal] = None
    price_per_hour: Decimal = Field(..., ge=0)
    min_rent_hours: int = Field(1, ge=1)

class StudioProfileCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    address: str
    legal_entity_info: Optional[str] = None  # ИНН, ОГРН, реквизиты


class ScheduleTemplateCreate(BaseModel):
    photographer_id: Optional[int] = None
    room_id: Optional[int] = None
    day_of_week: int = Field(..., ge=1, le=7, description="1 - Понедельник, 7 - Воскресенье")
    start_time: time
    end_time: time

    @field_validator('end_time')
    @classmethod
    def validate_times(cls, v, info):
        values = info.data
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time должно быть позже start_time')
        return v

class ScheduleExceptionCreate(BaseModel):
    photographer_id: Optional[int] = None
    room_id: Optional[int] = None
    date: date
    is_day_off: bool = False
    custom_start_time: Optional[time] = None
    custom_end_time: Optional[time] = None


class OrderItemRequest(BaseModel):
    photographer_id: Optional[int] = None
    photographer_service_id: Optional[int] = None
    studio_room_id: Optional[int] = None
    start_time: datetime
    end_time: datetime

class OrderCreate(BaseModel):
    order_type: OrderType
    items: List[OrderItemRequest] = Field(..., description="Позиции заказа (услуга фотографа и/или аренда зала)")

    @field_validator('items')
    @classmethod
    def validate_order_items(cls, v, info):
        if not v:
            raise ValueError("Заказ должен содержать хотя бы одну позицию")
        return v

class OrderResponse(BaseModel):
    id: int
    client_id: int
    order_type: OrderType
    status: OrderStatus
    total_price: Decimal
    prepayment_amount: Decimal
    created_at: datetime

    class Config:
        from_attributes = True



class ReviewCreate(BaseModel):
    order_id: int
    target_photographer_id: Optional[int] = None
    target_studio_id: Optional[int] = None
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None