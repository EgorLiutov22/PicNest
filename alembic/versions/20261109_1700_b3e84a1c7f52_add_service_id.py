"""add service_id to order_items

Revision ID: 20261109_1700_b3e84a1c7f52
Revises: a7c41f2d8e60
Create Date: 2026-11-09 17:00:00.000000+00:00

Закрывает расхождение между моделью OrderItem и схемой БД: в модели
появилось поле service_id (универсальная ссылка на услугу ресурса),
но миграция добавляла только resource_type и resource_id.

Колонка nullable: у существующих строк услуги нет, а старые заказы
хранят её в photographer_service_id.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e84a1c7f52'
down_revision: Union[str, None] = 'a7c41f2d8e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'order_items',
        sa.Column('service_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'order_items_service_id_fkey',
        'order_items',
        'photographer_services',
        ['service_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'order_items_service_id_fkey',
        'order_items',
        type_='foreignkey',
    )
    op.drop_column('order_items', 'service_id')
