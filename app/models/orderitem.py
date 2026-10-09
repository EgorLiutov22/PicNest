from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, TYPE_CHECKING


from sqlalchemy import (
    DECIMAL, 
    DateTime, ForeignKey, CheckConstraint, Index, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.photographerservice import PhotographerService

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="SET NULL"))
    photographer_service_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_services.id", ondelete="SET NULL"))
    studio_room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_rooms.id", ondelete="SET NULL"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixed_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    fixed_conditions: Mapped[Dict[str, Any]] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND studio_room_id IS NULL) OR (photographer_id IS NULL AND studio_room_id IS NOT NULL)",
            name="check_item_owner"
        ),
        Index("idx_order_items_room_time", "studio_room_id", "start_time", "end_time", postgresql_where=(studio_room_id.isnot(None))),
        Index("idx_order_items_photographer_time", "photographer_id", "start_time", "end_time", postgresql_where=(photographer_id.isnot(None))),
    )

   
    order: Mapped["Order"] = relationship(back_populates="items")
    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="order_items")
    photographer_service: Mapped[Optional["PhotographerService"]] = relationship(back_populates="order_items")
    studio_room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="order_items")
