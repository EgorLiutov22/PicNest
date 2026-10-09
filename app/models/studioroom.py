from __future__ import annotations
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String, Text, DECIMAL, ForeignKey
)
from sqlalchemy.orm import  Mapped, mapped_column, relationship

from app.models.base import Base

class StudioRoom(Base):
    __tablename__ = "studio_rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(ForeignKey("studio_profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    area: Mapped[Optional[int]] = mapped_column()
    ceiling_height: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 1))
    price_per_hour: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    min_rent_hours: Mapped[int] = mapped_column(default=1)

    studio: Mapped["StudioProfile"] = relationship(back_populates="rooms")
    schedule_templates: Mapped[List["ScheduleTemplate"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    schedule_exceptions: Mapped[List["ScheduleException"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    schedule_blocks: Mapped[List["ScheduleBlock"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="studio_room")
