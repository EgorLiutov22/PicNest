"""allow universal resource pointer in check_item_owner

Revision ID: d9e1b7c40a58
Revises: c5d2f8a91b04
Create Date: 2026-11-09 19:00:00.000000+00:00

Constraint check_item_owner требовал ровно одно из photographer_id/studio_room_id.
Новый тип ресурса (визажист, осветитель) не имеет своей колонки, поэтому
запись такого заказа падала с IntegrityError.

Теперь достаточно заполненного resource_type. Для старых строк правило
не меняется: строка без resource_type по-прежнему требует ровно одно
из двух legacy-полей.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'd9e1b7c40a58'
down_revision: Union[str, None] = 'c5d2f8a91b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('check_item_owner', 'order_items', type_='check')
    op.create_check_constraint(
        'check_item_owner',
        'order_items',
        "resource_type IS NOT NULL "
        "OR (photographer_id IS NOT NULL AND studio_room_id IS NULL) "
        "OR (photographer_id IS NULL AND studio_room_id IS NOT NULL)",
    )


def downgrade() -> None:
    # Строки нового типа ресурса не проходят старое правило. Без очистки
    # добавление constraint упадёт, а приложение на старом коде такие
    # заказы всё равно не прочитает.
    op.execute(
        """
        DELETE FROM order_items
        WHERE resource_type IS NOT NULL
          AND resource_type NOT IN ('photographer', 'studio_room')
          AND photographer_id IS NULL
          AND studio_room_id IS NULL
        """
    )
    op.drop_constraint('check_item_owner', 'order_items', type_='check')
    op.create_check_constraint(
        'check_item_owner',
        'order_items',
        "(photographer_id IS NOT NULL AND studio_room_id IS NULL) "
        "OR (photographer_id IS NULL AND studio_room_id IS NOT NULL)",
    )
