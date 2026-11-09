from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import Range, TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ResourceOccupancy(Base):
    """Занятый интервал ресурса: бронь или ручная блокировка.

    Единственная таблица, в которую пишется занятость. Пересечения
    запрещены exclusion constraint'ом в БД (occupancy_no_overlap), поэтому
    проверка «свободно ли» перед INSERT не нужна: гонки между запросами
    физически невозможны.

    Освобождение слота — released_at, а не удаление строк: история
    сохраняется, а частичный GiST-индекс держит в себе только живые
    интервалы.
    """

    __tablename__ = "resource_occupancy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(nullable=False)

    period: Mapped[Range] = mapped_column(TSTZRANGE, nullable=False)

    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    order_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=True
    )
    block_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_blocks.id", ondelete="CASCADE"), nullable=True
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_resource_occupancy_lookup", "resource_type", "resource_id", "period"),
        Index("idx_resource_occupancy_expires", "expires_at"),
    )
