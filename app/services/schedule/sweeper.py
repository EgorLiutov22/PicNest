"""
Фоновая чистка просроченных холдов брони.

Холд неоплаченного заказа освобождается по expires_at. В условие
частичного индекса now() вписать нельзя (предикат обязан быть immutable),
поэтому делает это отдельная задача, а не сама БД.

Задача живёт в процессе приложения: при рестарте она просто стартует
заново. Несколько реплик не мешают друг другу — expire_stale_holds
берёт строки через FOR UPDATE SKIP LOCKED.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.db import async_session_maker
from app.services.schedule.occupancy import expire_stale_holds

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _sweep_loop(interval: int) -> None:
    while True:
        try:
            async with async_session_maker() as session:
                released = await expire_stale_holds(session)
                await session.commit()
            if released:
                logger.info("Освобождено просроченных холдов: %s", released)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Ошибка одного прохода не должна убивать задачу: иначе холды
            # перестанут освобождаться до рестарта процесса.
            logger.exception("Ошибка при чистке просроченных холдов")

        await asyncio.sleep(interval)


def start_occupancy_sweeper(settings) -> None:
    """Запускает фоновую задачу, если она включена в настройках."""
    global _task

    if not getattr(settings, "OCCUPANCY_SWEEP_ENABLED", True):
        logger.info("Чистка просроченных холдов отключена настройками")
        return

    if _task is not None and not _task.done():
        return

    interval = int(getattr(settings, "OCCUPANCY_SWEEP_INTERVAL_SECONDS", 60))
    _task = asyncio.create_task(_sweep_loop(interval))
    logger.info("Чистка просроченных холдов запущена (интервал %s с)", interval)


async def stop_occupancy_sweeper() -> None:
    """Останавливает фоновую задачу перед завершением процесса."""
    global _task

    if _task is None:
        return

    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    finally:
        _task = None
