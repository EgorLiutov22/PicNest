from __future__ import annotations
from datetime import date, datetime, time
from typing import Optional, List


from sqlalchemy import (
    String, Text, Integer, DECIMAL, Boolean, Date, TIME,
    DateTime, ForeignKey, Enum as SQLEnum, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ScheduleBlock(Base):
    """Модель для блокировки временных слотов.
    
    Используется для ручного блокирования периодов времени фотографов или залов
    фотостудий для предотвращения двойного бронирования при сторонних заказах.
    """
    
    __tablename__ = "schedule_blocks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_rooms.id", ondelete="CASCADE"))
    # Интервал в UTC: блокировка «с 14 до 16» невыразима датой,
    # без времени начала и окончания.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR (photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_block_owner"
        ),
        CheckConstraint("end_at > start_at", name="check_block_range"),
        Index("idx_schedule_blocks_dates", "start_at", "end_at"),
    )

    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="schedule_blocks")
    room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="schedule_blocks")


class ScheduleTemplate(Base):
    """Модель недельного шаблона расписания.
    
    Определяет регулярное рабочее время по дням недели для фотографов или залов фотостудий.
    """
    
    __tablename__ = "schedule_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photographer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("photographer_profiles.id", ondelete="CASCADE"))
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studio_rooms.id", ondelete="CASCADE"))
    day_of_week: Mapped[int] = mapped_column(nullable=False)  # 1-7 (понедельник-воскресенье)
    start_time: Mapped[time] = mapped_column(TIME, nullable=False)
    end_time: Mapped[time] = mapped_column(TIME, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR (photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_template_owner"
        ),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="check_day_of_week"),
        CheckConstraint("end_time > start_time", name="check_template_time"),
        # Уникальность задаётся частичными индексами в миграции:
        # составной unique по (photographer_id, room_id) не ограничивал
        # ничего — NULL в Postgres не равен другому NULL.
    )

    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="schedule_templates")
    room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="schedule_templates")


class ScheduleException(Base):
    """Модель исключения из расписания.
    
    Позволяет назначать конкретные даты выходными днями или устанавливать кастомное время работы.
    Имеет приоритет над недельным шаблоном для конкретной даты.
    """
    
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
        Index("idx_schedule_exceptions_date", "date"),
    )

    photographer: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="schedule_exceptions")
    room: Mapped[Optional["StudioRoom"]] = relationship(back_populates="schedule_exceptions")
