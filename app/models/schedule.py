from __future__ import annotations
from datetime import date, time
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
    start_datetime: Mapped[date] = mapped_column(Date, nullable=False)
    end_datetime: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR (photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_block_owner"
        ),
        Index("idx_schedule_blocks_dates", "start_datetime", "end_datetime"),
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
        Index("idx_schedule_templates_owner", "photographer_id", "room_id", unique=True),
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


# ============================================================================
# Add relationships to existing models
# ============================================================================

async def add_schedule_relationships(db):
    """Добавляет связи с расписанием к существующим моделям.
    
    Эта функция должна быть вызвана один раз при инициализации БД для добавления
    обратной связи между PhotographerProfile/StudioRoom и таблицами расписания.
    """
    from sqlalchemy import text
    
    # Проверяем, существуют ли уже колонки schedule_blocks в photographer_profiles
    try:
        await db.execute(text("""
            ALTER TABLE photographer_profiles 
            ADD CONSTRAINT fk_photographer_schedule_blocks
            FOREIGN KEY (id) REFERENCES schedule_blocks(photographer_id)
            ON DELETE CASCADE;
        """))
    except Exception:
        # Ожидаем ошибку если связь уже существует
        pass
    
    await db.commit()
