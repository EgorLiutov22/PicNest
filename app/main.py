"""
Основное приложение FastAPI для PicNest Marketplace.

Этот модуль содержит:
- Инициализацию приложения FastAPI
- Настройку логирования (структурированное логирование через structlog)
- Middleware для обработки ошибок и логирования запросов
- Подключение всех роутеров API

Автор: PicNest Backend Team
Дата: 2026-10-20
"""

from datetime import datetime, timezone
import os
import time
import uuid
from typing import Callable

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response


from app.routers.auth import router as auth_router
from app.routers.orders import router as orders_router


# ============================================================================
# Настройка Sentry (интеграция для мониторинга ошибок)
# ============================================================================

def setup_sentry(settings) -> None:
    """Настраивает Sentry для отслеживания ошибок.
    
    Инициализируется только если SENTRY_DSN указан в настройках.
    Настраивает интеграцию с FastAPI и Starlette.
    
    Args:
        settings: Объект настроек приложения (Settings)
        
    Examples:
        >>> setup_sentry(settings)  # Если SENTRY_DSN не пустой
    """
    
    if not settings.SENTRY_DSN:
        return
    
    environment = settings.ENVIRONMENT or "development"
    debug = settings.DEBUG
    
    # Определяем traces_sample_rate в зависимости от окружения
    if environment == "production":
        traces_sample_rate = 0.1  # 10% транзакций для продакшена
        release_version = app.version if 'app' in globals() else "1.0.0"
    else:
        traces_sample_rate = 1.0  # Все транзакции в разработке
        release_version = f"{settings.APP_VERSION or '1.0.0'}-{environment}"
    
    try:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
            ],
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=1.0 if environment != "production" else 0.1,
            environment=environment,
            release=release_version,
            debug=debug,
            # Filter sensitive data
            before_send_transaction=before_send_transaction_filter,
        )
        
        from app.core.logging import get_logger
        logger = get_logger()
        logger.info(
            "Sentry initialized",
            environment=environment,
            traces_sample_rate=traces_sample_rate,
        )
        
    except Exception as e:
        from app.core.logging import get_logger
        logger = get_logger()
        logger.error(f"Failed to initialize Sentry: {e}")


def before_send_transaction_filter(event, hint):
    """
    Фильтрует чувствительные данные перед отправкой в Sentry.
    
    Args:
        event: Событие Sentry
        hint: Дополнительная информация об ошибке
        
    Returns:
        Отфильтрованное событие или None (если не должно быть отправлено)
    """
    # Удаляем чувствительные данные из контекста
    contexts = event.get("contexts", {})
    user_context = contexts.get("user", {})
    
    if user_context:
        # Оставляем только email (если есть) и удаляем другие личные данные
        user_context.pop("id", None)
        user_context.pop("username", None)
        user_context.pop("ip_address", None)
    
    return event


# ============================================================================
# Настройка Prometheus метрик
# ============================================================================

def setup_prometheus_metrics(app) -> Instrumentator:
    """Настраивает Prometheus instrumentation для FastAPI приложения.
    
    Args:
        app: FastAPI приложение
        
    Returns:
        Настроенный Instrumentator
        
    Examples:
        >>> instrumentator = setup_prometheus_metrics(app)
    """
    
    from app.core.logging import get_logger, get_environment
    logger = get_logger()
    environment = get_environment()
    
    # Проверяем что Prometheus включен через переменную окружения
    prometheus_enabled = os.environ.get("PROMETHEUS_ENABLED", "true").lower() == "true"
    
    if not prometheus_enabled:
        logger.debug("Prometheus metrics disabled (PROMETHEUS_ENABLED=false)")
        return Instrumentator()
    
    try:
        # Настройка Instrumentator
        instrumentator = Instrumentator(
            should_gather_latency=True,
            should_include_latency_histogram=True,
            should_group_status_codes=True,
            should_ignore_verbosity=False,
            should_respect_env_var=True,
            env_var_name="PROMETHEUS_ENABLED",
            metric_namespace="picnest",
            metric_subsystem="api",
        )
        
        # Исключаем чувствительные endpoint'ы
        instrumentator.excluded_handlers([
            "/docs",      # Swagger UI
            "/redoc",     # ReDoc
            "/openapi.json",  # OpenAPI spec
            "/health",    # Health check (не нужно мониторить)
            "/metrics",   # Сам эндпоинт метрик (чтобы избежать рекурсии)
        ])
        
        instrumentator.instrument(app).add()
        
        logger.info(
            "Prometheus metrics instrumentation configured",
            environment=environment,
            prometheus_enabled=prometheus_enabled,
        )
        
        return instrumentator
        
    except Exception as e:
        logger.error(f"Failed to setup Prometheus metrics: {e}")
        raise


# ============================================================================
# Endpoint для экспорта метрик Prometheus (только для внутренних IP)
# ============================================================================

@app.get("/metrics")
async def metrics_endpoint(request: Request):
    """Эндпоинт для экспорта метрик Prometheus.
    
    Доступен только из внутренней сети (для безопасности).
    Возвращает метрики в формате text/plain для парсинга Prometheus.
    
    Returns:
        Response с метриками в формате Prometheus
        
    Examples:
        # Из внутренней сети:
        curl http://localhost:8000/metrics
        
        # Или через Prometheus scrape:
        metrics_endpoint: http://api.internal:8000/metrics
    """
    
    from app.core.logging import get_logger
    logger = get_logger()
    
    # Проверяем что запрос из внутренней сети
    client_ip = request.client.host if request.client else "unknown"
    allowed_ips = ["127.0.0.1", "localhost"]  # Расширить список при необходимости
    
    # Разрешаем только localhost и внутренние IP (пример)
    if not any(client_ip.startswith(prefix) for prefix in ["127.", "192.168.", "10."]):
        logger.warning(
            "Запрещенный доступ к /metrics из внешнего IP",
            client_ip=client_ip,
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Доступ к метрикам разрешен только из внутренней сети"},
        )
    
    # Логируем запрос (опционально)
    logger.info("Request to /metrics endpoint", client_ip=client_ip)
    
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    
    return Response(
        content=generate_latest(),
        status_code=200,
        media_type=CONTENT_TYPE_LATEST,
    )


# ============================================================================
# Инициализация FastAPI приложения
# ============================================================================

app = FastAPI(
    title="PicNest Marketplace API",
    description=(
        "RESTful API для маркетплейса фотостудий и фотографов с управлением расписанием и заказами.\n\n"
        "**Основные возможности:**\n"
        "- Бронирование фотографов и залов фотостудий\n"
        "- Управление жизненным циклом заказов (создание, подтверждение, отмена)\n"
        "- Структурированное логирование и мониторинг ошибок\n"
        "- Интеграция с Sentry для отслеживания ошибок\n"
        "- Rate limiting для защиты от злоупотреблений и атак\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================================
# Регистрация CORS middleware для защиты от атак
# ============================================================================

from app.core.config import get_settings
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(",") if settings.CORS_ALLOWED_ORIGINS else ["*"],
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS.split(",") if settings.CORS_ALLOW_METHODS else ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=settings.CORS_ALLOW_HEADERS.split(",") if settings.CORS_ALLOW_HEADERS else ["Authorization", "Content-Type", "X-Requested-With", "Accept"],
)

# ============================================================================
# Регистрация middleware для защиты от XSS и других атак
# ============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable):
    """Добавляет заголовки безопасности во все ответы.
    
    Защищает от:
    - XSS (Cross-Site Scripting)
    - Clickjacking
    - MIME type sniffing
    - Browser cache attacks
    """
    
    from app.core.config import get_settings
    settings = get_settings()
    
    response = await call_next(request)
    
    # X-Content-Type-Options: prevents MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # X-Frame-Options: prevents clickjacking (DENY or SAMEORIGIN)
    if settings.DEBUG:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    else:
        response.headers["X-Frame-Options"] = "DENY"
    
    # X-XSS-Protection: legacy XSS filter (for older browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Strict-Transport-Security (HSTS): forces HTTPS connections
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    # Content-Security-Policy: restricts allowed content sources
    if not settings.DEBUG:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    
    # Referrer-Policy: controls referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Cache-Control for sensitive endpoints (optional)
    if request.url.path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    
    return response

# ============================================================================
# Регистрация SlowAPI middleware для rate limiting
# ============================================================================

from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ============================================================================
# Middleware: Генерация request_id и передача в контекст логирования
# ============================================================================

@app.middleware("http")
async def generate_request_id(request: Request, call_next: Callable):
    """Генерирует уникальный request_id (UUID) для каждого запроса.
    
    request_id передается в заголовке ответа и сохраняется в контексте логирования.
    Это позволяет отслеживать все логи связанные с одним запросом.
    
    Args:
        request: Объект запроса FastAPI
        call_next: Следующий middleware или endpoint
        
    Returns:
        Response объекта от сервера
        
    Examples:
        Request ID в заголовках ответа:
            X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
    """
    
    # Генерируем request_id если его нет в запросе
    request_id = request.headers.get("x-request-id")
    
    if not request_id:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    else:
        request.state.request_id = request_id
    
    # Начинаем измерение времени выполнения
    start_time = time.time()
    
    # Обрабатываем запрос
    response = await call_next(request)
    
    # Добавляем request_id в заголовок ответа
    response.headers["x-request-id"] = request_id
    
    # Измеряем время выполнения и сохраняем в state
    process_time = (time.time() - start_time) * 1000  # В миллисекундах
    request.state.process_time_ms = process_time
    
    return response


# ============================================================================
# Middleware: Логирование всех запросов
# ============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    """Логгирует все HTTP запросы и ответы.
    
    Логирует:
    - Метод запроса (GET, POST, PUT, DELETE)
    - Путь запроса
    - IP адрес клиента
    - Статус код ответа
    - Время выполнения
    
    Args:
        request: Объект запроса FastAPI
        call_next: Следующий middleware или endpoint
        
    Returns:
        Response объекта от сервера
    """
    
    from app.core.logging import get_logger, LogContext
    
    logger = get_logger()
    
    # Сохраняем метод и путь для логирования
    method = request.method
    path = request.url.path
    
    # Устанавливаем контекст для логирования
    LogContext.set_endpoint(path, method)
    
    # Получаем IP адрес клиента (учитываем прокси)
    client_ip = request.client.host if request.client else "unknown"
    
    # Начинаем измерение времени выполнения
    start_time = time.time()
    
    try:
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Измеряем время выполнения
        process_time = (time.time() - start_time) * 1000  # В миллисекундах
        
        # Логгируем успешный запрос
        logger.info(
            "HTTP request processed",
            method=method,
            path=path,
            status_code=response.status_code,
            client_ip=client_ip,
            process_time_ms=f"{process_time:.2f}",
        )
        
        return response
        
    except Exception as e:
        # Измеряем время выполнения при ошибке
        process_time = (time.time() - start_time) * 1000
        
        # Логгируем ошибку запроса
        logger.error(
            "HTTP request failed",
            method=method,
            path=path,
            client_ip=client_ip,
            process_time_ms=f"{process_time:.2f}",
            error=str(e),
            exc_info=True,
        )
        
        # Перевыбрасываем исключение для обработки глобальными обработчиками
        raise


# ============================================================================
# Health Check Endpoint
# ============================================================================

@app.get("/health")
async def health_check():
    """Проверка статуса приложения (Health Check).
    
    Проверяет:
    - Статус БД (PostgreSQL/SQLite)
    - Версию приложения
    
    Возвращает JSON со статусом здоровья системы.
    
    Returns:
        JSON с информацией о здоровье приложения
        
    Examples:
        Response:
        {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": "2026-10-20T15:30:00Z"
        }
        
        При ошибке БД:
        {
            "status": "degraded",
            "version": "1.0.0",
            "database_status": "error",
            "timestamp": "2026-10-20T15:30:00Z"
        }
    """
    
    from app.core.logging import get_logger
    
    logger = get_logger()
    
    # Проверяем статус БД
    database_status = "unknown"
    try:
        from app.core.db import get_async_engine, use_postgresql
        
        engine = get_async_engine()
        
        if engine is not None:
            database_status = "connected" if use_postgresql else "sqlite_connected"
        else:
            database_status = "error"
            
    except Exception as e:
        logger.error("Ошибка проверки статуса БД", error=str(e))
        database_status = "error"
    
    # Формируем ответ
    health_response = {
        "status": "healthy" if database_status != "error" else "degraded",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "database_status": database_status,
    }
    
    # Логируем статус (если что-то не так)
    if health_response["status"] != "healthy":
        logger.warning("Приложение работает в режиме degraded", **health_response)
    
    return health_response


# ============================================================================
# Инициализация приложения при старте
# ============================================================================

@app.on_event("startup")
async def startup():
    """Инициализация приложения при запуске.
    
    Выполняется один раз при старте сервера:
    - Настройка логгера (структурированное логирование)
    - Инициализация базы данных
    - Инициализация Sentry (если настроен SENTRY_DSN)
    """
    
    from app.core.logging import setup_app_logging, get_logger
    
    logger = get_logger()
    
    # Получаем настройки приложения
    from app.core.config import get_settings
    settings = get_settings()
    
    # Настройка структурированного логирования
    # Определяем окружение и формат логов
    environment = settings.ENVIRONMENT or "development"
    
    if environment == "production":
        setup_app_logging(log_level="WARNING", output_format="json")
        logger.info(
            "Application started in PRODUCTION mode",
            log_format="JSON",
            log_level="WARNING",
        )
    else:
        setup_app_logging(log_level="DEBUG", output_format="console")
        logger.debug(
            "Application started in DEVELOPMENT mode",
            log_format="Console (colored)",
            log_level="DEBUG",
        )
    
    # Инициализация Sentry для отслеживания ошибок
    setup_sentry(settings)
    
    # Инициализация базы данных
    from app.core.db import init_db
    
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")


# ============================================================================
# Подключение роутеров API
# ============================================================================

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(orders_router, prefix="/api/v1/orders", tags=["Orders Management"])
# TODO: Подключить роутер расписания после создания модели ScheduleBlock в БД


__all__ = ["app"]
