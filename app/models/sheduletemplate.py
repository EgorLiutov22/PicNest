from __future__ import annotations
from datetime import  time
from typing import Optional

from sqlalchemy import ( TIME,  ForeignKey,  CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class ScheduleTemplate(Base):
    __tablename__ = "schedule_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_rooms.id", ondelete="CASCADE"))
    day_of_week: Mapped[int] = mapped_column(nullable=False)
    start_time: Mapped[time] = mapped_column(TIME, nullable=False)
    end_time: Mapped[time] = mapped_column(TIME, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR (photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_template_owner"
        ),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="check_day_of_week")
    )

    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="schedule_templates")
    room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="schedule_templates")