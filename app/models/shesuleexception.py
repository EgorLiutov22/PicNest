from __future__ import annotations
from datetime import date, time
from typing import  Optional


from sqlalchemy import (
    String, Text, Integer, DECIMAL, Boolean, Date, TIME, 
    DateTime, ForeignKey, Enum as SQLEnum, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class ScheduleException(Base):
    __tablename__ = "schedule_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_rooms.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_start_time: Mapped[Optional[time]] = mapped_column(TIME)
    custom_end_time: Mapped[Optional[time]] = mapped_column(TIME)

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR (photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_exception_owner"
        ),
    )

    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="schedule_exceptions")
    room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="schedule_exceptions")