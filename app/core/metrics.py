"""
Метрики Prometheus для мониторинга производительности PicNest Marketplace API.

Этот модуль настраивает экспортер метрик через prometheus-fastapi-instrumentator:
- Количество запросов по endpoint'ам и HTTP методам
- Время выполнения запросов (histogram)
- Ошибки и исключения
- Статус коды ответов
- Кастомные метрики для бизнес-логики

Автор: PicNest Backend Team
Дата: 2026-10-20
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import (
    Histogram,
    Counter,
    Gauge,
)


# ============================================================================
# Определения метрик Prometheus
# ============================================================================

class MetricsDefinitions:
    """Определения всех метрик для мониторинга API."""
    
    # HTTP запросы
    http_requests_total = None  # Counter - общее количество запросов
    http_request_duration_seconds = None  # Histogram - время выполнения
    
    # Ошибки по типам
    errors_total = None  # Counter - общее количество ошибок
    validation_errors_total = None  # Counter - ошибки валидации
    database_errors_total = None  # Counter - ошибки базы данных
    authentication_errors_total = None  # Counter - ошибки аутентификации
    
    # Бизнес-метрики (заказы)
    orders_created_total = None  # Counter - количество созданных заказов
    orders_confirmed_total = None  # Counter - количество подтвержденных заказов
    orders_cancelled_total = None  # Counter - количество отмененных заказов
    
    # Статус приложения
    app_start_time = None  # Gauge - время запуска приложения (Unix timestamp)
    active_connections = None  # Gauge - активные подключения


def initialize_metrics() -> dict:
    """Инициализирует все метрики Prometheus.
    
    Returns:
        Словарь с инициализированными метриками
        
    Examples:
        >>> metrics = initialize_metrics()
        >>> metrics['http_requests_total'].inc()  # Увеличить счетчик
    """
    
    from app.core.logging import get_logger
    
    logger = get_logger()
    
    metrics = {}
    
    try:
        # HTTP метрики (автоматически от Instrumentator)
        metrics["http_requests_total"] = Counter(
            name="http_requests_total",
            documentation="Общее количество HTTP запросов к API",
            labelnames=["method", "endpoint", "status_code"],
            namespace="picnest",
        )
        
        metrics["http_request_duration_seconds"] = Histogram(
            name="http_request_duration_seconds",
            documentation="Время выполнения HTTP запросов в секундах",
            labelnames=["method", "endpoint", "status_code"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            namespace="picnest",
        )
        
        # Метрики ошибок
        metrics["errors_total"] = Counter(
            name="errors_total",
            documentation="Общее количество ошибок сервера",
            labelnames=["error_type"],
            namespace="picnest",
        )
        
        metrics["validation_errors_total"] = Counter(
            name="validation_errors_total",
            documentation="Количество ошибок валидации входных данных",
            labelnames=["endpoint", "field"],
            namespace="picnest",
        )
        
        metrics["database_errors_total"] = Counter(
            name="database_errors_total",
            documentation="Количество ошибок базы данных",
            labelnames=["operation"],
            namespace="picnest",
        )
        
        metrics["authentication_errors_total"] = Counter(
            name="authentication_errors_total",
            documentation="Количество ошибок аутентификации/авторизации",
            labelnames=["reason"],
            namespace="picnest",
        )
        
        # Бизнес-метрики (заказы)
        metrics["orders_created_total"] = Counter(
            name="orders_created_total",
            documentation="Общее количество созданных заказов",
            labelnames=["order_type", "client_id_hash"],
            namespace="picnest",
        )
        
        metrics["orders_confirmed_total"] = Counter(
            name="orders_confirmed_total",
            documentation="Количество подтвержденных заказов",
            labelnames=["performer_id_hash"],
            namespace="picnest",
        )
        
        metrics["orders_cancelled_total"] = Counter(
            name="orders_cancelled_total",
            documentation="Количество отмененных заказов",
            labelnames=["reason", "refund_percentage"],
            namespace="picnest",
        )
        
        # Метрики состояния приложения
        import time as time_module
        
        metrics["app_start_time"] = Gauge(
            name="picnest_app_start_time_seconds",
            documentation="Unix timestamp времени запуска приложения",
            labelnames=[],
            namespace="",
        )
        metrics["app_start_time"].set(time_module.time())
        
        metrics["active_connections"] = Gauge(
            name="picnest_active_connections",
            documentation="Количество активных соединений с базой данных",
            labelnames=["connection_type"],  # "pool" или "single"
            namespace="",
        )
        
        logger.info("Prometheus metrics initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize Prometheus metrics: {e}")
    
    return metrics


# ============================================================================
# Настройка Instrumentator для FastAPI
# ============================================================================

def setup_prometheus_instrumentator(
    app,
    should_gather_latency=True,
    should_include_latency_histogram=True,
) -> Instrumentator:
    """Настраивает Prometheus Instrumentator для FastAPI приложения.
    
    Args:
        app: FastAPI приложение
        should_gather_latency: Включать ли метрики времени выполнения
        should_include_latency_histogram: Включать ли histogram (распределение)
        
    Returns:
        Настроенный Instrumentator
        
    Examples:
        >>> instrumentator = setup_prometheus_instrumentator(app)
        >>> app = instrumentator.instrument(app)
    """
    
    from app.core.logging import get_logger
    
    logger = get_logger()
    
    try:
        # Создаем Instrumentator с настройками по умолчанию
        instrumentator = Instrumentator(
            should_gather_latency=should_gather_latency,
            should_include_latency_histogram=should_include_latency_histogram,
            
            # Настройка экспорта метрик
            should_group_status_codes=True,  # Группировать status codes (2xx, 4xx, 5xx)
            should_ignore_verbosity=False,   # Логировать все уровни
            
            # Кастомные настройки
            should_respect_env_var=True,     # Учитывать ENVIRONMENT переменную
            env_var_name="PROMETHEUS_ENABLED",
            
            # Имена метрик
            metric_namespace="picnest",
            metric_subsystem="api",
        )
        
        # Добавляем кастомные экспортеры
        instrumentator.add(
            counter_exposer=instrumentator.default_counter_exposer,
            histogram_exposer=instrumentator.default_histogram_exposer,
        )
        
        # Настраиваем фильтры для чувствительных endpoint'ов (опционально)
        instrumentator.excluded_handlers([
            "/docs",      # Swagger UI
            "/redoc",     # ReDoc
            "/openapi.json",  # OpenAPI spec
            "/health",    # Health check (не нужно мониторить постоянно)
        ])
        
        logger.info("Prometheus Instrumentator configured successfully")
        
        return instrumentator
        
    except Exception as e:
        logger.error(f"Failed to configure Prometheus Instrumentator: {e}")
        raise


# ============================================================================
# Кастомные метрики для бизнес-логики
# ============================================================================

class BusinessMetrics:
    """Класс для работы с бизнес-метриками (заказы, платежи и т.д.)."""
    
    def __init__(self):
        from app.core.logging import get_logger
        self.logger = get_logger()
        
        # Инициализируем метрики если еще не сделана
        try:
            metrics = initialize_metrics()
            self.metrics = metrics
            
            # Сохраняем ссылки на счетчики
            self.orders_created = metrics.get("orders_created_total")
            self.orders_confirmed = metrics.get("orders_confirmed_total")
            self.orders_cancelled = metrics.get("orders_cancelled_total")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize BusinessMetrics: {e}")
            self.orders_created = None
            self.orders_confirmed = None
            self.orders_cancelled = None
    
    def track_order_creation(
        self,
        order_type: str,
        client_id: int,
    ) -> None:
        """Отслеживает создание заказа.
        
        Args:
            order_type: Тип заказа (photographer_only, studio_only, combined)
            client_id: ID клиента (хэшируется для приватности)
        """
        if self.orders_created is None:
            return
        
        try:
            # Хэшируем client_id для защиты персональных данных
            client_id_hash = f"hash_{abs(hash(str(client_id))) % 10000}"
            
            self.orders_created.inc(
                labels={
                    "order_type": order_type,
                    "client_id_hash": client_id_hash,
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to track order creation metric: {e}")
    
    def track_order_confirmation(
        self,
        performer_id: int,
    ) -> None:
        """Отслеживает подтверждение заказа исполнителем.
        
        Args:
            performer_id: ID исполнителя (хэшируется)
        """
        if self.orders_confirmed is None:
            return
        
        try:
            performer_id_hash = f"hash_{abs(hash(str(performer_id))) % 10000}"
            
            self.orders_confirmed.inc(
                labels={
                    "performer_id_hash": performer_id_hash,
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to track order confirmation metric: {e}")
    
    def track_order_cancellation(
        self,
        reason: str,
        refund_percentage: float,
    ) -> None:
        """Отслеживает отмену заказа.
        
        Args:
            reason: Причина отмены
            refund_percentage: Процент возврата (0-100)
        """
        if self.orders_cancelled is None:
            return
        
        try:
            # Ограничиваем длину reason для label
            truncated_reason = reason[:50] if len(reason) > 50 else reason
            
            self.orders_cancelled.inc(
                labels={
                    "reason": truncated_reason,
                    "refund_percentage": str(int(refund_percentage)),
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to track order cancellation metric: {e}")


# ============================================================================
# Глобальный экземпляр BusinessMetrics
# ============================================================================

_business_metrics_instance = None


def get_business_metrics() -> BusinessMetrics:
    """Получает глобальный экземпляр BusinessMetrics.
    
    Returns:
        Экземпляр BusinessMetrics
        
    Examples:
        >>> metrics = get_business_metrics()
        >>> metrics.track_order_creation("photographer_only", client_id=123)
    """
    
    global _business_metrics_instance
    
    if _business_metrics_instance is None:
        _business_metrics_instance = BusinessMetrics()
    
    return _business_metrics_instance


# ============================================================================
# Middleware для учета метрик запросов
# ============================================================================

async def metrics_request_counter(
    request,
    start_time: float,
) -> dict:
    """Собирает информацию о запросе для метрик.
    
    Args:
        request: Объект запроса FastAPI
        start_time: Время начала обработки
        
    Returns:
        Словарь с ключевыми данными для метрик
    """
    
    from app.core.logging import get_logger
    
    logger = get_logger()
    
    try:
        # Получаем данные из request
        method = request.method
        path = request.url.path
        
        # Удаляем query params и ID для обобщения (например, /orders/{id} -> /orders)
        normalized_path = _normalize_endpoint_path(path)
        
        return {
            "method": method,
            "endpoint": normalized_path,
            "raw_path": path,
            "start_time": start_time,
        }
        
    except Exception as e:
        logger.warning(f"Failed to extract metrics data from request: {e}")
        return {}


def _normalize_endpoint_path(path: str) -> str:
    """Нормализует путь endpoint'а для группировки метрик.
    
    Примеры:
        /api/v1/orders/123 -> /api/v1/orders/{id}
        /api/v1/auth/login -> /api/v1/auth/login
        /api/v1/orders/{order_id}/confirm -> /api/v1/orders/{order_id}/confirm
    
    Args:
        path: Исходный путь
        
    Returns:
        Нормализованный путь
    """
    
    # Регулярное выражение для замены числовых ID на {id}
    import re
    
    normalized = path
    
    # Заменяем UUID и другие идентификаторы
    patterns = [
        r"/\d+",           # Числовые ID (например, /orders/123)
        r"/[a-f0-9-]{8}-[a-f0-9-]{4}-[a-f0-9-]{4}-[a-f0-9-]{4}-[a-f0-9-]{12}",  # UUID
    ]
    
    for pattern in patterns:
        normalized = re.sub(pattern, "/{id}", normalized)
    
    return normalized


# ============================================================================
# Экспорт всех публичных функций
# ============================================================================

__all__ = [
    "MetricsDefinitions",
    "initialize_metrics",
    "setup_prometheus_instrumentator",
    "BusinessMetrics",
    "get_business_metrics",
    "metrics_request_counter",
    "_normalize_endpoint_path",
]
