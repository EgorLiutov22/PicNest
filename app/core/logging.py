"""
Структурированное логирование для PicNest Marketplace.

Этот модуль настраивает структурированное логирование с использованием structlog:
- JSON формат для продакшена (логгеры ELK, CloudWatch и т.д.)
- Цветной вывод для разработки (консоль)
- Контекстные поля: request_id, user_id, endpoint

Автор: PicNest Backend Team
Дата: 2026-10-20
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import structlog
from structlog.contextvars import merge_contextvars, clear_contextvars
from structlog.processors import JSONRenderer, CallTimeFieldProcessor, NamePrepend
from structlog.stdlib import ProcessorFormatter, add_log_level, make_filtering_bound_logger
import re


# ============================================================================
# Настройка форматов логирования
# ============================================================================

# ============================================================================
# Маскирование чувствительных данных в логах
# ============================================================================

SENSITIVE_FIELDS = [
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret_key",
    "api_key",
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"\+?[0-9][0-9]{7,14}")


def mask_sensitive_data(record: Dict[str, Any]) -> Dict[str, Any]:
    """Маскирует чувствительные данные в логах.
    
    Args:
        record: Запись лога
        
    Returns:
        Запись с замаскированными чувствительными полями
    """
    
    masked_record = dict(record)
    context = masked_record.get("_context", {})
    
    # Маскируем чувствительные ключи
    for key in SENSITIVE_FIELDS:
        if key in context:
            value = str(context[key])
            # Маскируем токены и пароли (оставляем только первые 4 символа)
            masked_record["_context"][key] = f"{value[:4]}***MASKED***"
    
    # Маскируем email адреса
    if "message" in record:
        message = str(record["msg"])
        masked_message = EMAIL_REGEX.sub("***@***.***", message)
        masked_message = PHONE_REGEX.sub("***-***-****", masked_message)
        masked_record["msg"] = masked_message
    
    # Маскируем email и phone в контексте
    if "email" in context:
        masked_record["_context"]["email"] = EMAIL_REGEX.sub("***@***.***", str(context["email"]))
    
    if "phone" in context:
        masked_record["_context"]["phone"] = PHONE_REGEX.sub("***-***-****", str(context["phone"]))
    
    return masked_record


def get_environment() -> str:
    """Определяет окружение (production/development)."""
    
    # Можно расширить логику определения окружения
    env = __import__("os").environ.get("ENVIRONMENT", "development")
    return env.lower().strip()


# ============================================================================
# Форматирование логов для консоли (разработка)
# ============================================================================

def console_processor(
    logger: logging.Logger,
    method_name: str,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Форматирует лог для вывода в консоль с цветом."""
    
    # Извлекаем контекстные поля
    context = record.get("_context", {})
    
    # Добавляем метаданные
    formatted_record = {
        "timestamp": datetime.fromisoformat(record["asctime"]).strftime("%Y-%m-%d %H:%M:%S"),
        "level": record["levelname"],
        "logger": record["name"],
        "message": record["msg"],
        **context,
    }
    
    return formatted_record


# ============================================================================
# Форматирование логов для продакшена (JSON)
# ============================================================================

def production_processor(
    logger: logging.Logger,
    method_name: str,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Форматирует лог в JSON формат."""
    
    # Извлекаем контекстные поля
    context = record.get("_context", {})
    
    # Добавляем метаданные
    formatted_record = {
        "timestamp": datetime.fromisoformat(record["asctime"]).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["levelname"],
        "logger": record["name"],
        "message": record["msg"],
        **context,
    }
    
    return formatted_record


# ============================================================================
# Инициализация structlog
# ============================================================================

def setup_logging(log_level: str = "INFO", output_format: str = "console") -> None:
    """Настраивает структурированное логирование.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        output_format: Формат вывода ('console' или 'json')
        
    Examples:
        >>> setup_logging(log_level="INFO", output_format="console")  # Разработка
        >>> setup_logging(log_level="WARNING", output_format="json")   # Продакшен
    """
    
    environment = get_environment()
    
    # Настройка базового логгера Python
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    
    # Контекстные обработчики для structlog
    shared_processors = [
        add_log_level,
        structlog.processors.add_log_level,  # Для совместимости с разными версиями
        mask_sensitive_data,  # Маскирование чувствительных данных
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        structlog.contextvars.merge_contextvars,
    ]
    
    if output_format == "json":
        # JSON формат для продакшена
        structlog.configure(
            processors=[
                *shared_processors,
                production_processor,
                JSONRenderer(),
            ],
            wrapper_class=make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Консольный формат с цветом для разработки
        structlog.configure(
            processors=[
                *shared_processors,
                console_processor,
                structlog.dev.ConsoleRenderer(
                    colors=True,
                    sort_keys=True,
                    column_widths={
                        "level": 8,
                        "logger": 20,
                        "message": 50,
                    },
                ),
            ],
            wrapper_class=make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


# ============================================================================
# Контекстные поля для логирования
# ============================================================================

class LogContext:
    """Контекст для логирования с автоматическим управлением."""
    
    @staticmethod
    def set_request_id() -> str:
        """Генерирует и устанавливает request_id (UUID)."""
        
        request_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        return request_id
    
    @staticmethod
    def get_request_id() -> str | None:
        """Получает текущий request_id из контекста."""
        
        return structlog.contextvars.clear_contextvars().get("request_id")  # type: ignore[return-value]
    
    @staticmethod
    def set_user_id(user_id: int) -> None:
        """Устанавливает user_id в контекст."""
        
        structlog.contextvars.bind_contextvars(user_id=user_id)
    
    @staticmethod
    def set_endpoint(endpoint: str, method: str = "GET") -> None:
        """Устанавливает endpoint и метод HTTP в контекст."""
        
        structlog.contextvars.bind_contextvars(
            endpoint=endpoint,
            http_method=method,
        )
    
    @staticmethod
    def set_duration(duration_ms: float) -> None:
        """Устанавливает время выполнения запроса в миллисекундах."""
        
        structlog.contextvars.bind_contextvars(request_duration_ms=duration_ms)
    
    @staticmethod
    def clear() -> None:
        """Очищает все контекстные поля."""
        
        clear_contextvars()


# ============================================================================
# Основной логгер
# ============================================================================

def get_logger(module_name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Получает настроенный логгер для указанного модуля.
    
    Args:
        module_name: Имя модуля (автоматически определяется из caller)
        
    Returns:
        Структурированный BoundLogger
        
    Examples:
        >>> logger = get_logger()  # Автоматическое определение модуля
        >>> logger.info("Запрос обработан", request_id="abc-123")
        {'timestamp': '2026-10-20T15:30:00.123Z', 'level': 'info', 
         'logger': 'app.routers.auth', 'message': 'Запрос обработан', 
         'request_id': 'abc-123'}
    """
    
    return structlog.get_logger(module_name)


def setup_app_logging(log_level: str = "INFO", output_format: str = "console") -> None:
    """Настраивает логирование для приложения.
    
    Вызывается при старте приложения в main.py.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        output_format: Формат вывода ('console' или 'json')
    """
    
    setup_logging(log_level=log_level, output_format=output_format)


__all__ = [
    "setup_app_logging",
    "get_logger",
    "LogContext",
    "production_processor",
    "console_processor",
]
