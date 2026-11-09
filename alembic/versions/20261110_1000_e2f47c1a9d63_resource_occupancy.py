"""resource occupancy: exclusion constraint for double bookings

Revision ID: e2f47c1a9d63
Revises: d9e1b7c40a58
Create Date: 2026-11-10 10:00:00.000000+00:00

Занятость ресурса хранится в одной таблице resource_occupancy, а
пересечения запрещает exclusion constraint. Проверка «свободно ли»
перед вставкой больше не нужна: между проверкой и вставкой не остаётся
окна, в которое может влезть параллельный запрос.

Интервал полуоткрытый — [start, end). Бронь 14:00-15:00 и 15:00-16:00
не пересекаются.

Освобождение слота — released_at, а не DELETE: constraint действует
только на живые строки (WHERE released_at IS NULL), поэтому индекс не
раздувается отменёнными заказами, а история сохраняется.

Также исправляются расписания:
- schedule_blocks: Date -> timestamptz, иначе блокировка «с 14 до 16»
  невыразима;
- schedule_templates: составной unique (photographer_id, room_id) не
  ограничивал ничего, потому что NULL не равен другому NULL. Заменён
  частичными индексами; добавлен CHECK end_time > start_time.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e2f47c1a9d63'
down_revision: Union[str, None] = 'd9e1b7c40a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # btree_gist нужен для оператора "=" по varchar/int внутри GiST-индекса.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # --- Занятость ресурсов ------------------------------------------------
    op.create_table(
        'resource_occupancy',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column(
            'period',
            postgresql.TSTZRANGE(),
            nullable=False,
        ),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('order_item_id', sa.Integer(), nullable=True),
        sa.Column('block_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['order_item_id'], ['order_items.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['block_id'], ['schedule_blocks.id'], ondelete='CASCADE'
        ),
        sa.CheckConstraint(
            "kind IN ('booking', 'block')",
            name='check_occupancy_kind',
        ),
        sa.CheckConstraint(
            "(kind = 'booking' AND order_item_id IS NOT NULL AND block_id IS NULL) "
            "OR (kind = 'block' AND block_id IS NOT NULL AND order_item_id IS NULL)",
            name='check_occupancy_source',
        ),
        sa.CheckConstraint(
            "NOT isempty(period)", name='check_occupancy_nonempty'
        ),
        sa.CheckConstraint(
            "lower_inc(period) AND NOT upper_inc(period)",
            name='check_occupancy_half_open',
        ),
    )
    op.create_index(
        'idx_resource_occupancy_lookup',
        'resource_occupancy',
        ['resource_type', 'resource_id', 'period'],
    )
    op.create_index(
        'idx_resource_occupancy_expires',
        'resource_occupancy',
        ['expires_at'],
    )
    # Предикат частичного индекса обязан быть immutable, поэтому now() сюда
    # не вписать. Просроченные холды освобождает фоновый job (released_at).
    op.execute(
        """
        ALTER TABLE resource_occupancy
          ADD CONSTRAINT occupancy_no_overlap
          EXCLUDE USING gist (
              resource_type WITH =,
              resource_id   WITH =,
              period        WITH &&
          ) WHERE (released_at IS NULL)
        """
    )

    # --- Блокировки: дата -> интервал --------------------------------------
    op.drop_index('idx_schedule_blocks_dates', table_name='schedule_blocks')
    op.alter_column(
        'schedule_blocks', 'start_datetime',
        new_column_name='start_at',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.Date(),
        postgresql_using='start_datetime::timestamp AT TIME ZONE \'UTC\'',
    )
    op.alter_column(
        'schedule_blocks', 'end_datetime',
        new_column_name='end_at',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.Date(),
        postgresql_using='end_datetime::timestamp AT TIME ZONE \'UTC\'',
    )
    op.create_check_constraint(
        'check_block_range', 'schedule_blocks', 'end_at > start_at'
    )
    op.create_index(
        'idx_schedule_blocks_dates', 'schedule_blocks', ['start_at', 'end_at']
    )

    # --- Шаблоны: рабочий уникальный индекс ---------------------------------
    op.drop_index('idx_schedule_templates_owner', table_name='schedule_templates')
    op.create_check_constraint(
        'check_template_time', 'schedule_templates', 'end_time > start_time'
    )
    op.create_index(
        'ux_tpl_photographer_day',
        'schedule_templates',
        ['photographer_id', 'day_of_week'],
        unique=True,
        postgresql_where=sa.text('photographer_id IS NOT NULL'),
    )
    op.create_index(
        'ux_tpl_room_day',
        'schedule_templates',
        ['room_id', 'day_of_week'],
        unique=True,
        postgresql_where=sa.text('room_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ux_tpl_room_day', table_name='schedule_templates')
    op.drop_index('ux_tpl_photographer_day', table_name='schedule_templates')
    op.drop_constraint('check_template_time', 'schedule_templates', type_='check')
    op.create_index(
        'idx_schedule_templates_owner',
        'schedule_templates',
        ['photographer_id', 'room_id'],
        unique=True,
    )

    op.drop_index('idx_schedule_blocks_dates', table_name='schedule_blocks')
    op.drop_constraint('check_block_range', 'schedule_blocks', type_='check')
    op.alter_column(
        'schedule_blocks', 'start_at',
        new_column_name='start_datetime',
        type_=sa.Date(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using='start_at::date',
    )
    op.alter_column(
        'schedule_blocks', 'end_at',
        new_column_name='end_datetime',
        type_=sa.Date(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using='end_at::date',
    )
    op.create_index(
        'idx_schedule_blocks_dates', 'schedule_blocks',
        ['start_datetime', 'end_datetime'],
    )

    op.drop_table('resource_occupancy')
