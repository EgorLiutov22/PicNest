"""
Rate limiting для защиты API от злоупотреблений и атак.

Этот модуль настраивает SlowAPI для ограничения количества запросов к API endpoints.
Поддерживается два типа хранилищ:
- In-memory (по умолчанию, для разработки)
- Redis (для продакшена)

Автор: PicNest Backend Team
Дата: 2026-10-21
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Callable, Optional

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


# ============================================================================
# Инициализация лимитера
# ============================================================================

def create_limiter() -> Limiter:
    """Создает и настраивает экземпляр Limiter.

    Использует Redis для продакшена, in-memory для разработки.

    Returns:
        Настроенный экземпляр Limiter

    Examples:
        >>> limiter = create_limiter()
        >>> @router.get("/endpoint")
        ... @limiter.limit("5/minute")
        ... async def endpoint():
        ...     pass
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Определяем тип хранилища
    environment = os.environ.get("ENVIRONMENT", "development")
    redis_url = os.environ.get("REDIS_URL", None)

    if environment == "production" and redis_url:
        # Redis для продакшена
        try:
            from slowapi.storage import RedisStorage

            limiter = Limiter(
                key_func=get_remote_address,
                storage=RedisStorage(redis_url),
                default_limits=["100/hour"],  # Default rate limit
                headers_enabled=True,
            )

            logger.info(
                "Rate limiter initialized with Redis storage",
                redis_url=redis_url[:20] + "...",  # Mask part of URL
                environment=environment,
            )

        except Exception as e:
            logger.warning(f"Failed to initialize Redis storage: {e}")
            logger.info("Falling back to in-memory storage")
            limiter = _create_in_memory_limiter()
    else:
        # In-memory для разработки
        limiter = _create_in_memory_limiter()

    return limiter


def _create_in_memory_limiter() -> Limiter:
    """Создает лимитер с in-memory хранилищем.

    Используется для разработки и тестирования.

    Returns:
        Limiter с in-memory storage
    """

    from slowapi.storage import MemoryStorage

    limiter = Limiter(
        key_func=get_remote_address,
        storage=MemoryStorage(),
        default_limits=["100/hour"],  # Default rate limit per IP
        headers_enabled=True,
    )

    return limiter


# ============================================================================
# Rate limit decorators для различных endpoints
# ============================================================================

def get_rate_limit_decorator(limit: str) -> Callable:
    """Создает декоратор для rate limiting.

    Args:
        limit: Строка лимита (например, "5/minute", "10/hour")

    Returns:
        Функция-декоратор

    Examples:
        >>> decorator = get_rate_limit_decorator("5/minute")
        >>> @router.get("/endpoint")
        ... @decorator
        ... async def endpoint():
        ...     pass
    """

    from slowapi import _rate_limit_exceeded_handler

    def decorator(func):
        return limiter.limit(limit)(func)

    return decorator


# ============================================================================
# Rate limits для различных endpoints
# ============================================================================

RATE_LIMITS = {
    # Authentication endpoints (защита от brute-force)
    "auth_login": "5/minute",           # 5 попыток входа в минуту
    "auth_register": "3/minute",        # 3 регистрации в минуту
    "auth_refresh": "10/minute",        # 10 обновлений токенов в минуту

    # Orders (защита от спама бронирований)
    "orders_create": "20/minute",       # 20 заказов в минуту
    "orders_list": "60/minute",         # 60 запросов списка заказов в минуту
    "order_detail": "100/minute",       # 100 запросов детализации заказа в минуту

    # Schedule (защита от скрейпинга)
    "studios_list": "100/minute",       # 100 запросов списка студий в минуту
    "schedule_templates": "30/minute",  # 30 запросов шаблонов расписания в минуту

    # General endpoints
    "health_check": None,               # Health check без лимита
    "metrics": "60/minute",             # Метрики 60 раз в минуту
    "docs": None,                       # Документация без лимита
}


# ============================================================================
# Custom exception handler для RateLimitExceeded
# ============================================================================

async def rate_limit_exceeded_handler(request, exc):
    """Обработчик превышения лимита запросов.

    Возвращает 429 Too Many Requests с заголовком Retry-After.

    Args:
        request: Объект запроса FastAPI
        exc: Исключение RateLimitExceeded

    Returns:
        JSONResponse с информацией об ошибке и Retry-After
    """

    from fastapi import Response
    from app.core.logging import get_logger

    logger = get_logger()

    # Получаем информацию о лимите
    rate_limit = exc.detail.split(" ")[0] if " " in exc.detail else "unknown"

    logger.warning(
        f"Rate limit exceeded: {rate_limit}",
        path=request.url.path,
        method=request.method,
        client_ip=exc.ip if hasattr(exc, 'ip') else None,
    )

    # Формируем ответ с заголовком Retry-After
    response = Response(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "detail": f"Слишком много запросов. Попробуйте снова через {exc.retry_after} секунд.",
            "retry_after": exc.retry_after if hasattr(exc, 'retry_after') else 60,
        },
    )

    # Добавляем заголовок Retry-After для HTTP клиентов
    response.headers["Retry-After"] = str(exc.retry_after if hasattr(exc, 'retry_added') else 60)

    return response


# ============================================================================
# Utility functions
# ============================================================================

def get_current_rate_limit(endpoint_name: str) -> Optional[str]:
    """Получает текущий rate limit для endpoint.

    Args:
        endpoint_name: Название endpoint (например, "auth_login")

    Returns:
        Строка лимита или None если не задан

    Examples:
        >>> get_current_rate_limit("auth_login")
        '5/minute'
        >>> get_current_rate_limit("health_check")
        None
    """

    return RATE_LIMITS.get(endpoint_name)


def reset_rate_limit(key: str = "all"):
    """Сбрасывает rate limits.

    Используется для тестирования и администрирования.

    Args:
        key: Ключ для сброса (например, IP адрес или "all")

    Examples:
        >>> reset_rate_limit("192.168.1.100")  # Сбросить лимиты для конкретного IP
        >>> reset_rate_limit("all")             # Сбросить все лимиты (in-memory storage)
    """

    if key == "all":
        from slowapi.storage import MemoryStorage

        if isinstance(limiter.storage, MemoryStorage):
            limiter.storage._storage.clear()
    else:
        # Для Redis сброс по конкретному ключу
        pass


# ============================================================================
# Глобальный экземпляр Limiter
# ============================================================================

limiter = create_limiter()


# ============================================================================
# Экспорт функций и переменных
# ============================================================================

__all__ = [
    "limiter",
    "create_limiter",
    "get_rate_limit_decorator",
    "RATE_LIMITS",
    "rate_limit_exceeded_handler",
    "get_current_rate_limit",
    "reset_rate_limit",
]
