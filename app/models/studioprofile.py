from __future__ import annotations
from decimal import Decimal
from typing import List, Optional


from sqlalchemy import (
    String, Text, DECIMAL, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class StudioProfile(Base):
    __tablename__ = "studio_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    legal_entity_info: Mapped[Optional[str]] = mapped_column(Text)
    rating: Mapped[Decimal] = mapped_column(DECIMAL(3, 2), default=0.00)

    user: Mapped["User"] = relationship(back_populates="studio_profile")
    rooms: Mapped[List["StudioRoom"]] = relationship(back_populates="studio", cascade="all, delete-orphan")