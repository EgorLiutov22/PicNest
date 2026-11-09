"""backfill resource_type/resource_id/service_id from legacy columns

Revision ID: c5d2f8a91b04
Revises: b3e84a1c7f52
Create Date: 2026-11-09 18:00:00.000000+00:00

Переносит существующие позиции заказов на универсальные поля:
- photographer_id   -> resource_type='photographer', resource_id=photographer_id
- studio_room_id    -> resource_type='studio_room',  resource_id=studio_room_id
- photographer_service_id -> service_id

Ограничение check_item_owner гарантирует, что у каждой строки заполнено
ровно одно из photographer_id/studio_room_id, поэтому строки без
resource_type остаться не должно. Строки, у которых оба NULL, появились
бы только при отключённом constraint — их не трогаем.

Колонки остаются nullable: в промежутке между этой миграцией и удалением
старых колонок в БД ещё могут писаться строки без новых полей.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'c5d2f8a91b04'
down_revision: Union[str, None] = 'b3e84a1c7f52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE order_items
        SET resource_type = 'photographer',
            resource_id   = photographer_id,
            service_id    = COALESCE(service_id, photographer_service_id)
        WHERE photographer_id IS NOT NULL
          AND resource_type IS NULL
        """
    )
    op.execute(
        """
        UPDATE order_items
        SET resource_type = 'studio_room',
            resource_id   = studio_room_id
        WHERE studio_room_id IS NOT NULL
          AND resource_type IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE order_items
        SET resource_type = NULL,
            resource_id   = NULL
        WHERE resource_type = 'studio_room'
          AND resource_id = studio_room_id
        """
    )
    op.execute(
        """
        UPDATE order_items
        SET service_id = NULL
        WHERE resource_type = 'photographer'
          AND resource_id = photographer_id
          AND service_id = photographer_service_id
        """
    )
    op.execute(
        """
        UPDATE order_items
        SET resource_type = NULL,
            resource_id   = NULL
        WHERE resource_type = 'photographer'
          AND resource_id = photographer_id
        """
    )
