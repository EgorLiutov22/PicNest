from __future__ import annotations
from datetime import datetime
from typing import Optional


from sqlalchemy import ( Text, 
    DateTime, ForeignKey, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.base import Base

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="SET NULL"))
    target_studio_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_profiles.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="CURRENT_TIMESTAMP")

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="check_review_rating"),
    )

    order: Mapped["Order"] = relationship(back_populates="review")
    author: Mapped["User"] = relationship(back_populates="reviews")