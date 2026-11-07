"""Метрики Prometheus для PicNest.

Модуль закрывает две вещи:

1. Инструментирование FastAPI через prometheus-fastapi-instrumentator —
   счётчики запросов, задержки, коды ответов.
2. Экспорт метрик с поддержкой нескольких uvicorn-воркеров.

Приложение запускается с ``--workers 2``. По умолчанию prometheus_client
хранит метрики в памяти процесса, поэтому каждый воркер отдавал бы свой
набор, а /metrics показывал данные случайного воркера. Для корректного
сбора задаётся ``PROMETHEUS_MULTIPROC_DIR``: воркеры пишут в общую папку,
а экспорт читает её через MultiProcessCollector.
"""

from __future__ import annotations

import os

from prometheus_fastapi_instrumentator import Instrumentator


MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

# Эндпоинты, которые не нужно учитывать в метриках
EXCLUDED_HANDLERS = [
    "/metrics",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
]


def setup_metrics(app) -> Instrumentator | None:
    """Подключает инструментирование FastAPI.

    Возвращает None, если метрики отключены через PROMETHEUS_ENABLED=false.
    """
    if os.environ.get("PROMETHEUS_ENABLED", "true").lower() != "true":
        return None

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=EXCLUDED_HANDLERS,
    )
    # instrument() регистрирует метрики, add() создал бы собственный /metrics.
    # Свой эндпоинт нужен, чтобы ограничить доступ по IP и поддержать
    # мультипроцессный экспорт.
    instrumentator.instrument(app)
    return instrumentator


def render_metrics() -> bytes:
    """Сериализует метрики в формате Prometheus."""
    from prometheus_client import REGISTRY, CollectorRegistry, generate_latest

    if MULTIPROC_DIR:
        from prometheus_client import multiprocess

        # Одноразовый реестр только на чтение: собирает файлы всех воркеров.
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)

    return generate_latest(REGISTRY)
