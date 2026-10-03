from __future__ import annotations
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String, Text,  DECIMAL, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class PhotographerService(Base):
    __tablename__ = "photographer_services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photographer_id: Mapped[int] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    photos_count: Mapped[Optional[int]] = mapped_column()
    delivery_days: Mapped[Optional[int]] = mapped_column()
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    photographer: Mapped["PhotographerProfile"] = relationship(back_populates="services")
    order_items: Mapped[List["OrderItem"]] = relationship(back_populates="photographer_service")