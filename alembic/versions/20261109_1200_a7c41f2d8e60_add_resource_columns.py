"""add generic resource columns to order_items

Revision ID: 20261109_1200_a7c41f2d8e60
Revises: f1de57ddfd90
Create Date: 2026-11-09 12:00:00.000000+00:00

Добавляет в order_items универсальные поля resource_type/resource_id.
Старые колонки photographer_id, photographer_service_id и studio_room_id
намеренно остаются: текущий код заказов продолжает на них работать, а
перенос данных и удаление колонок — отдельный шаг после переключения
чтения и записи.

Обе колонки nullable: существующие строки их не имеют, а NOT NULL
нельзя добавить без значения по умолчанию.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c41f2d8e60'
down_revision: Union[str, None] = 'f1de57ddfd90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'order_items',
        sa.Column('resource_type', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'order_items',
        sa.Column('resource_id', sa.Integer(), nullable=True),
    )

    # Индекс под будущие проверки пересечений по универсальной паре.
    # Частичный, как и существующие: строки без resource_id не участвуют.
    op.create_index(
        'idx_order_items_resource_time',
        'order_items',
        ['resource_type', 'resource_id', 'start_time', 'end_time'],
        unique=False,
        postgresql_where=sa.text('resource_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('idx_order_items_resource_time', table_name='order_items')
    op.drop_column('order_items', 'resource_id')
    op.drop_column('order_items', 'resource_type')
