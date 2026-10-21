"""
Глобальные обработчики ошибок для PicNest Marketplace API.

Этот модуль регистрирует обработчики всех кастомных исключений и стандартных
HTTP-исключений FastAPI. Все ошибки преобразуются в единый формат ответа
и автоматически логируются.

Автор: PicNest Backend Team
Дата: 2026-10-21
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


# ============================================================================
# Форматирование ответов об ошибках
# ============================================================================

def error_response(
    status_code: int,
    detail: str = None,
    error_code: str = None,
    timestamp: datetime = None,
    request_id: str = None,
) -> Dict[str, Any]:
    """Формирует стандартный ответ об ошибке.

    Args:
        status_code: HTTP статус-код ответа
        detail: Человечески читаемое описание ошибки
        error_code: Код ошибки для программной обработки
        timestamp: Время возникновения ошибки (по умолчанию - сейчас)
        request_id: ID запроса для трассировки

    Returns:
        Словарь с данными для JSON-ответа

    Examples:
        >>> response = error_response(404, "User not found", "USER_NOT_FOUND")
        {
            "error_code": "USER_NOT_FOUND",
            "detail": "User not found",
            "timestamp": "2026-10-21T10:30:00Z",
            "request_id": "abc-123"
        }
    """

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    response_data: Dict[str, Any] = {
        "error_code": error_code or "UNKNOWN_ERROR",
        "detail": detail or "An unexpected error occurred.",
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Добавляем request_id если указан
    if request_id:
        response_data["request_id"] = request_id

    return response_data


# ============================================================================
# Обработчик для кастомных исключений AppException
# ============================================================================

async def app_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обработчик всех кастомных исключений приложения.

    Args:
        request: Объект запроса FastAPI
        exc: Исключение типа AppException или его подкласс

    Returns:
        JSONResponse с информацией об ошибке
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Получаем информацию об исключении
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    error_code = getattr(exc, "error_code", "UNKNOWN_ERROR")

    # Получаем request_id из контекста
    request_id = getattr(request.state, "request_id", None)

    # Логируем ошибку в зависимости от уровня
    if status_code >= 500:
        logger.error(
            f"Server error [{error_code}]: {detail}",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            exception_type=type(exc).__name__,
        )
    else:
        # 4xx ошибки - предупреждение или информация
        logger.warning(
            f"Client error [{error_code}]: {detail}",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            exception_type=type(exc).__name__,
        )

    # Формируем ответ
    return JSONResponse(
        status_code=status_code,
        content=error_response(
            status_code=status_code,
            detail=detail,
            error_code=error_code,
            request_id=request_id,
        ),
    )


# ============================================================================
# Обработчик для RequestValidationError (валидация Pydantic)
# ============================================================================

async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Обработчик ошибок валидации входных данных.

    Обрабатывает ошибки от FastAPI/Pydantic когда пользователь передает
    некорректные данные (неверный формат, отсутствующие поля и т.д.).

    Args:
        request: Объект запроса FastAPI
        exc: Исключение RequestValidationError

    Returns:
        JSONResponse с детализированными ошибками валидации
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Форматируем ошибки валидации
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })

    # Получаем request_id из контекста
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        "Validation error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        errors=errors,
    )

    # Формируем ответ с деталями ошибок
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "Validation failed",
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": request_id,
        },
    )


# ============================================================================
# Обработчик для Pydantic ValidationError (альтернативный)
# ============================================================================

async def pydantic_validation_exception_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    """Обработчик ошибок валидации Pydantic.

    Иногда FastAPI может использовать ValidationError напрямую вместо
    RequestValidationError. Этот обработчик обеспечивает совместимость.

    Args:
        request: Объект запроса FastAPI
        exc: Исключение ValidationError

    Returns:
        JSONResponse с информацией об ошибке валидации
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Преобразуем ошибки Pydantic в формат FastAPI
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc.get("loc", ["unknown"]))),
            "message": error["msg"],
            "type": error["type"],
        })

    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        "Pydantic validation error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        errors=errors,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "Validation failed",
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": request_id,
        },
    )


# ============================================================================
# Обработчик для HTTPException (стандартные исключения FastAPI)
# ============================================================================

async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Обработчик стандартных HTTP-исключений FastAPI.

    Обрабатывает HTTPException которые могут быть подняты через
    fastapi.HTTPException или автоматически генерироваться фреймворком.

    Args:
        request: Объект запроса FastAPI
        exc: Исключение HTTPException

    Returns:
        JSONResponse с информацией об ошибке
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Получаем данные из исключения
    status_code = getattr(exc, "status_code", 500)
    detail = exc.detail or str(exc)

    # Пытаемся распарсить detail если это JSON (иногда FastAPI возвращает dict)
    if isinstance(detail, dict):
        detail_str = str(detail.get("detail", str(detail)))
    else:
        detail_str = str(detail)

    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"HTTP error [{status_code}]",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        status_code=status_code,
        detail=detail_str,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": f"HTTP_{status_code}",
            "detail": detail_str,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": request_id,
        },
    )


# ============================================================================
# Обработчик для всех необработанных исключений (500 Internal Server Error)
# ============================================================================

async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Глобальный обработчик всех необработанных ошибок.

    Этот обработчик перехватывает все исключения которые не были
    обработаны другими handlers. Используется для логирования критических
    ошибок и предотвращения падения приложения с пустым ответом.

    Args:
        request: Объект запроса FastAPI
        exc: Необработанное исключение

    Returns:
        JSONResponse с общей информацией об ошибке (без деталей для безопасности)
    """

    from app.core.logging import get_logger

    logger = get_logger()

    # Получаем request_id из контекста
    request_id = getattr(request.state, "request_id", None)

    # Логируем полную информацию об ошибке с traceback
    error_type = type(exc).__name__
    error_message = str(exc) if str(exc) else "No message provided"

    logger.error(
        f"Unhandled exception [{error_type}]: {error_message}",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        exc_info=True,  # Полный traceback
        error_type=error_type,
        error_message=error_message,
    )

    # Для продакшена не показываем детали ошибки пользователю
    # В режиме разработки можно включить детальную информацию

    from app.core.config import get_settings
    settings = get_settings()

    if settings.DEBUG:
        debug_detail = {
            "error_type": error_type,
            "error_message": error_message,
            "path": request.url.path,
            "method": request.method,
        }
        detail_str = f"Internal server error. Details: {debug_detail}"
    else:
        detail_str = "An unexpected error occurred. Please try again later or contact support."

    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": detail_str,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": request_id,
        },
    )


# ============================================================================
# Регистрация обработчиков в FastAPI приложении
# ============================================================================

def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует все обработчики ошибок в приложении.

    Этот метод должен быть вызван после создания экземпляра FastAPI,
    но перед подключением роутеров.

    Args:
        app: Экземпляр FastAPI приложения

    Examples:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> register_exception_handlers(app)
    """

    # Кастомные исключения приложения (AppException и все подклассы)
    app.add_exception_handler(
        Exception,  # Используем Exception как базовый класс для всех кастомных исключений
        app_exception_handler,
    )

    # Ошибки валидации FastAPI/Pydantic
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    # Ошибки валидации Pydantic (альтернативный)
    try:
        from pydantic import ValidationError
        app.add_exception_handler(
            ValidationError,
            pydantic_validation_exception_handler,
        )
    except ImportError:
        pass  # Pydantic v1 использует другие механизмы

    # Стандартные HTTP-исключения FastAPI
    try:
        from fastapi import HTTPException
        app.add_exception_handler(
            HTTPException,
            http_exception_handler,
        )
    except ImportError:
        pass

    # Глобальный обработчик для всех необработанных ошибок
    app.add_exception_handler(
        Exception,  # Перехватываем все остальные исключения
        general_exception_handler,
    )


# ============================================================================
# Дополнительная утилита: получение контекста ошибки для логирования
# ============================================================================

def get_error_context(exception: Exception) -> Dict[str, Any]:
    """Извлекает контекстную информацию об ошибке.

    Args:
        exception: Исключение

    Returns:
        Словарь с информацией об ошибке
    """

    context = {
        "type": type(exception).__name__,
        "message": str(exception),
        "status_code": getattr(exception, "status_code", None),
        "error_code": getattr(exception, "error_code", None),
    }

    # Добавляем дополнительные атрибуты для специфичных исключений
    if hasattr(exception, "detail"):
        context["detail"] = exception.detail

    if hasattr(exception, "retry_after"):
        context["retry_after"] = exception.retry_after

    return context


# ============================================================================
# Экспорт функций
# ============================================================================

__all__ = [
    "error_response",
    "app_exception_handler",
    "validation_exception_handler",
    "pydantic_validation_exception_handler",
    "http_exception_handler",
    "general_exception_handler",
    "register_exception_handlers",
    "get_error_context",
]
