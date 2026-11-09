"""
Схемы каталога: студии, залы, фотографы, услуги и доступность.

Каталог отдельный от заказов: здесь только чтение справочников и
расписания. Ничего, что требует авторизации владельца.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CatalogModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StudioRoomShort(CatalogModel):
    id: int
    name: str
    description: Optional[str] = None
    area: Optional[int] = None
    ceiling_height: Optional[Decimal] = None
    price_per_hour: Decimal
    min_rent_hours: int


class StudioShort(CatalogModel):
    id: int
    title: str
    address: str
    rating: Decimal
    rooms_count: int = 0
    min_price_per_hour: Optional[Decimal] = None


class StudioDetail(StudioShort):
    description: Optional[str] = None
    rooms: List[StudioRoomShort] = Field(default_factory=list)


class PhotographerServiceShort(CatalogModel):
    id: int
    title: str
    description: Optional[str] = None
    duration_minutes: int
    photos_count: Optional[int] = None
    delivery_days: Optional[int] = None
    price: Decimal


class PhotographerShort(CatalogModel):
    id: int
    display_name: str
    avatar_url: Optional[str] = None
    rating: Decimal
    services_count: int = 0
    min_price: Optional[Decimal] = None


class PhotographerDetail(PhotographerShort):
    bio: Optional[str] = None
    legal_status: Optional[str] = None
    services: List[PhotographerServiceShort] = Field(default_factory=list)


class StudiosListResponse(CatalogModel):
    items: List[StudioShort]
    total: int
    skip: int
    limit: int


class PhotographersListResponse(CatalogModel):
    items: List[PhotographerShort]
    total: int
    skip: int
    limit: int


class BusyInterval(CatalogModel):
    start: datetime
    end: datetime
    kind: str


class FreeInterval(CatalogModel):
    start: datetime
    end: datetime


class AvailabilityResponse(CatalogModel):
    """Занятость ресурса на диапазон дат.

    Время в UTC. Свободные интервалы посчитаны как рабочие часы по
    шаблону минус занятость, поэтому клиенту не нужно повторять эту
    арифметику и он не может разойтись с сервером в трактовке.
    """
    resource_type: str
    resource_id: int
    timezone: str
    date_from: date
    date_to: date
    busy: List[BusyInterval] = Field(default_factory=list)
    free: List[FreeInterval] = Field(default_factory=list)
