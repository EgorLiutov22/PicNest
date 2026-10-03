from __future__ import annotations
from datetime import  datetime
from decimal import Decimal
from typing import Optional


from sqlalchemy import (
    String, Text, Integer, DECIMAL, Boolean, Date, TIME, 
    DateTime, ForeignKey, Enum as SQLEnum, CheckConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.base import Base

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    platform_commission: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="CURRENT_TIMESTAMP")

    order: Mapped["Order"] = relationship(back_populates="payments")