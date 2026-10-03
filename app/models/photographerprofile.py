from __future__ import annotations
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String, Text, DECIMAL, ForeignKey 
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class PhotographerProfile(Base):
    __tablename__ = "photographer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    legal_status: Mapped[Optional[str]] = mapped_column(String(50))
    verification_status: Mapped[str] = mapped_column(String(50), default="pending")
    rating: Mapped[Decimal] = mapped_column(DECIMAL(3, 2), default=0.00)

    user: Mapped["User"] = relationship(back_populates="photographer_profile")
    services: Mapped[List["PhotographerService"]] = relationship(back_populates="photographer", cascade="all, delete-orphan")
    schedule_templates: Mapped[List["ScheduleTemplate"]] = relationship(back_populates="photographer", cascade="all, delete-orphan")
    schedule_exceptions: Mapped[List["ScheduleException"]] = relationship(back_populates="photographer", cascade="all, delete-orphan")
    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="photographer")