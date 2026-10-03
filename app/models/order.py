from __future__ import annotations
from datetime import  datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
 DECIMAL, 
    DateTime, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import  Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.ordertype import OrderType
from app.models.orderstatus import OrderStatus

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(SQLEnum(OrderType), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus), default=OrderStatus.pending_payment, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    prepayment_amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="CURRENT_TIMESTAMP")

    client: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    review: Mapped[Optional["Review"]] = relationship(back_populates="order", uselist=False)