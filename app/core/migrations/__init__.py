"""
Модуль миграций базы данных PicNest.

Содержит скрипты для управления изменениями структуры БД.
"""

from app.core.migrations.add_schedule_block import (
    add_schedule_blocks_table,
    rollback_schedule_blocks_table,
)

__all__ = [
    "add_schedule_blocks_table",
    "rollback_schedule_blocks_table",
]
