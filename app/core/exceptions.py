"""
Кастомные исключения для PicNest Marketplace API.

Этот модуль определяет базовый класс AppException и все подклассы
для различных типов ошибок, которые могут возникать в системе.
Все исключения автоматически маппятся на соответствующие HTTP status codes.

Автор: PicNest Backend Team
Дата: 2026-10-21
"""

from __future__ import annotations

from fastapi import HTTPException


# ============================================================================
# Базовый класс для всех кастомных исключений приложения
# ============================================================================

class AppException(Exception):
    """Базовый класс для всех кастомных исключений приложения.

    Все кастомные исключения наследуются от этого класса и автоматически
    преобразуются в HTTP-ответы с соответствующим статус-кодом.

    Attributes:
        status_code (int): HTTP статус-код ответа (400, 401, 403, 404, 409, 429)
        detail (str): Человечески читаемое описание ошибки
        error_code (str): Код ошибки для программной обработки

    Examples:
        >>> raise NotFoundException("User not found", error_code="USER_NOT_FOUND")
        # Преобразуется в HTTPException(status_code=404, detail={"error_code": "USER_NOT_FOUND", ...})
    """

    def __init__(self, detail: str = None, error_code: str = None):
        """Инициализация исключения.

        Args:
            detail: Человечески читаемое описание ошибки
            error_code: Код ошибки для программной обработки

        Examples:
            >>> exc = AppException(detail="Invalid input", error_code="INVALID_INPUT")
            >>> assert exc.status_code == 500
            >>> assert exc.detail == "Invalid input"
            >>> assert exc.error_code == "INVALID_INPUT"
        """

        self.status_code = 500
        self.detail = detail or "An unexpected error occurred."
        self.error_code = error_code or "INTERNAL_ERROR"

        # Формируем полное сообщение для логирования
        super().__init__(f"[{self.error_code}] {detail}")


# ============================================================================
# Исключения с HTTP статус-кодом 400 (Bad Request) - Ошибки валидации
# ============================================================================

class ValidationException(AppException):
    """Исключение для ошибок валидации входных данных.

    Используется когда пользователь передает некорректные данные:
    - Неверный формат email
    - Недопустимые значения параметров
    - Отсутствующие обязательные поля

    Examples:
        >>> raise ValidationException(
        ...     detail="Invalid email format",
        ...     error_code="INVALID_EMAIL_FORMAT"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Validation error.", error_code=error_code or "VALIDATION_ERROR")
        self.status_code = 400


class InvalidInputException(ValidationException):
    """Исключение для некорректных входных данных.

    Примеры использования:
    - Недопустимое значение enum поля
    - Отрицательное число там, где должно быть положительное
    - Строка слишком длинная/короткая

    Examples:
        >>> raise InvalidInputException(
        ...     detail="Price must be positive",
        ...     error_code="INVALID_PRICE"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Invalid input data.", error_code=error_code or "INVALID_INPUT")


class MissingRequiredFieldException(ValidationException):
    """Исключение для отсутствующих обязательных полей.

    Examples:
        >>> raise MissingRequiredFieldException(
        ...     detail="Email is required",
        ...     error_code="MISSING_EMAIL"
        ... )
    """

    def __init__(self, field_name: str = None, detail: str = None, error_code: str = None):
        if not detail and field_name:
            detail = f"{field_name} is required."
        super().__init__(detail=detail, error_code=error_code or "MISSING_REQUIRED_FIELD")


# ============================================================================
# Исключения с HTTP статус-кодом 401 (Unauthorized) - Ошибки аутентификации
# ============================================================================

class AuthenticationException(AppException):
    """Исключение для ошибок аутентификации.

    Используется когда:
    - Неверный email/пароль
    - Истек срок действия токена
    - Токен не передан

    Examples:
        >>> raise AuthenticationException(
        ...     detail="Invalid email or password",
        ...     error_code="INVALID_CREDENTIALS"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Authentication failed.", error_code=error_code or "AUTHENTICATION_FAILED")
        self.status_code = 401


class InvalidCredentialsException(AuthenticationException):
    """Исключение для неверных учетных данных.

    Examples:
        >>> raise InvalidCredentialsException(
        ...     detail="Email or password is incorrect",
        ...     error_code="INVALID_CREDENTIALS"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Invalid credentials.", error_code=error_code or "INVALID_CREDENTIALS")


class TokenExpiredException(AuthenticationException):
    """Исключение для истекшего срока действия токена.

    Examples:
        >>> raise TokenExpiredException(
        ...     detail="Access token has expired",
        ...     error_code="TOKEN_EXPIRED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Token expired.", error_code=error_code or "TOKEN_EXPIRED")


class InvalidTokenException(AuthenticationException):
    """Исключение для невалидного токена.

    Examples:
        >>> raise InvalidTokenException(
        ...     detail="Invalid token format",
        ...     error_code="INVALID_TOKEN"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Invalid token.", error_code=error_code or "INVALID_TOKEN")


class TokenRequiredException(AuthenticationException):
    """Исключение когда токен отсутствует.

    Examples:
        >>> raise TokenRequiredException(
        ...     detail="Access token is required",
        ...     error_code="TOKEN_REQUIRED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Token required.", error_code=error_code or "TOKEN_REQUIRED")


# ============================================================================
# Исключения с HTTP статус-кодом 403 (Forbidden) - Ошибки авторизации
# ============================================================================

class ForbiddenException(AppException):
    """Исключение для недостаточных прав доступа.

    Используется когда:
    - Пользователь пытается получить доступ к чужим данным
    - Роль пользователя не имеет необходимых привилегий

    Examples:
        >>> raise ForbiddenException(
        ...     detail="You do not have permission to perform this action",
        ...     error_code="ACCESS_DENIED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Access denied.", error_code=error_code or "FORBIDDEN")
        self.status_code = 403


class InsufficientPermissionsException(ForbiddenException):
    """Исключение для недостаточных прав.

    Examples:
        >>> raise InsufficientPermissionsException(
        ...     detail="Admin role required",
        ...     error_code="INSUFFICIENT_PERMISSIONS"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Insufficient permissions.", error_code=error_code or "INSUFFICIENT_PERMISSIONS")


class UserInactiveException(ForbiddenException):
    """Исключение для неактивного пользователя.

    Examples:
        >>> raise UserInactiveException(
        ...     detail="Your account has been deactivated",
        ...     error_code="USER_INACTIVE"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "User inactive.", error_code=error_code or "USER_INACTIVE")


class EmailNotVerifiedException(ForbiddenException):
    """Исключение для не подтвержденного email.

    Examples:
        >>> raise EmailNotVerifiedException(
        ...     detail="Please verify your email address",
        ...     error_code="EMAIL_NOT_VERIFIED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Email not verified.", error_code=error_code or "EMAIL_NOT_VERIFIED")


# ============================================================================
# Исключения с HTTP статус-кодом 404 (Not Found) - Ресурс не найден
# ============================================================================

class NotFoundException(AppException):
    """Исключение когда ресурс не найден.

    Используется для всех случаев "не найдено":
    - Пользователь не существует
    - Заказ не найден
    - Студия удалена

    Examples:
        >>> raise NotFoundException(
        ...     detail="Order with id=123 not found",
        ...     error_code="ORDER_NOT_FOUND"
        ... )
    """

    def __init__(self, resource_type: str = None, resource_id: int = None, detail: str = None, error_code: str = None):
        if not detail:
            if resource_type and resource_id:
                detail = f"{resource_type} with id={resource_id} not found."
            elif resource_type:
                detail = f"{resource_type} not found."
            else:
                detail = "Resource not found."

        error_code = error_code or ("RESOURCE_NOT_FOUND" if resource_id else "NOT_FOUND")
        super().__init__(detail=detail, error_code=error_code)
        self.status_code = 404


class UserNotFoundException(NotFoundException):
    """Исключение когда пользователь не найден.

    Examples:
        >>> raise UserNotFoundException(user_id=123)
    """

    def __init__(self, user_id: int = None, detail: str = None, error_code: str = None):
        super().__init__(resource_type="User", resource_id=user_id, detail=detail, error_code=error_code or "USER_NOT_FOUND")


class OrderNotFoundException(NotFoundException):
    """Исключение когда заказ не найден.

    Examples:
        >>> raise OrderNotFoundException(order_id=123)
    """

    def __init__(self, order_id: int = None, detail: str = None, error_code: str = None):
        super().__init__(resource_type="Order", resource_id=order_id, detail=detail, error_code=error_code or "ORDER_NOT_FOUND")


class StudioNotFoundException(NotFoundException):
    """Исключение когда студия не найдена.

    Examples:
        >>> raise StudioNotFoundException(studio_id=123)
    """

    def __init__(self, studio_id: int = None, detail: str = None, error_code: str = None):
        super().__init__(resource_type="Studio", resource_id=studio_id, detail=detail, error_code=error_code or "STUDIO_NOT_FOUND")


class PhotographerNotFoundException(NotFoundException):
    """Исключение когда фотограф не найден.

    Examples:
        >>> raise PhotographerNotFoundException(photographer_id=123)
    """

    def __init__(self, photographer_id: int = None, detail: str = None, error_code: str = None):
        super().__init__(resource_type="Photographer", resource_id=photographer_id, detail=detail, error_code=error_code or "PHOTOGRAPHER_NOT_FOUND")


class RoomNotFoundException(NotFoundException):
    """Исключение когда зал студии не найден.

    Examples:
        >>> raise RoomNotFoundException(room_id=123)
    """

    def __init__(self, room_id: int = None, detail: str = None, error_code: str = None):
        super().__init__(resource_type="Room", resource_id=room_id, detail=detail, error_code=error_code or "ROOM_NOT_FOUND")


# ============================================================================
# Исключения с HTTP статус-кодом 409 (Conflict) - Конфликт операций
# ============================================================================

class ConflictException(AppException):
    """Исключение для конфликтов при выполнении операции.

    Используется когда:
    - Ресурс уже существует (дубликат email)
    - Попытка бронирования занятого слота
    - Невозможное изменение состояния

    Examples:
        >>> raise ConflictException(
        ...     detail="Email already registered",
        ...     error_code="EMAIL_ALREADY_EXISTS"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Conflict occurred.", error_code=error_code or "CONFLICT")
        self.status_code = 409


class EmailAlreadyExistsException(ConflictException):
    """Исключение когда email уже зарегистрирован.

    Examples:
        >>> raise EmailAlreadyExistsException(email="user@example.com")
    """

    def __init__(self, email: str = None, detail: str = None, error_code: str = None):
        if not detail and email:
            detail = f"Email {email} already registered."
        super().__init__(detail=detail or "Email already exists.", error_code=error_code or "EMAIL_ALREADY_EXISTS")


class SlotAlreadyBookedException(ConflictException):
    """Исключение когда слот бронирования уже занят.

    Examples:
        >>> raise SlotAlreadyBookedException(
        ...     studio_id=123,
        ...     start_time="2026-10-25T14:00:00",
        ...     end_time="2026-10-25T16:00:00"
        ... )
    """

    def __init__(self, studio_id: int = None, start_time: str = None, end_time: str = None, detail: str = None, error_code: str = None):
        if not detail and studio_id and start_time:
            detail = f"Slot {start_time} to {end_time} is already booked for studio {studio_id}."
        super().__init__(detail=detail or "Slot already booked.", error_code=error_code or "SLOT_ALREADY_BOOKED")


class BookingConflictException(ConflictException):
    """Исключение для конфликта бронирований.

    Примеры:
    - Пользователь уже имеет активное бронирование в это время
    - Пересекающиеся временные интервалы

    Examples:
        >>> raise BookingConflictException(
        ...     detail="You already have a booking at this time",
        ...     error_code="BOOKING_CONFLICT"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Booking conflict.", error_code=error_code or "BOOKING_CONFLICT")


class StateTransitionException(ConflictException):
    """Исключение для невозможного перехода состояния.

    Examples:
        >>> raise StateTransitionException(
        ...     detail="Cannot cancel an already completed order",
        ...     error_code="INVALID_STATE_TRANSITION"
        ... )
    """

    def __init__(self, current_state: str = None, target_state: str = None, detail: str = None, error_code: str = None):
        if not detail and current_state and target_state:
            detail = f"Cannot transition from {current_state} to {target_state}."
        super().__init__(detail=detail or "Invalid state transition.", error_code=error_code or "INVALID_STATE_TRANSITION")


# ============================================================================
# Исключения с HTTP статус-кодом 402 (Payment Required) - Ошибки платежей
# ============================================================================

class PaymentRequiredException(AppException):
    """Исключение когда требуется оплата.

    Используется для:
    - Неоплаченные заказы
    - Недостаточно средств на балансе
    - Отказано в оплате

    Examples:
        >>> raise PaymentRequiredException(
        ...     detail="Order payment required",
        ...     error_code="PAYMENT_REQUIRED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Payment required.", error_code=error_code or "PAYMENT_REQUIRED")
        self.status_code = 402


class InsufficientFundsException(PaymentRequiredException):
    """Исключение для недостаточных средств.

    Examples:
        >>> raise InsufficientFundsException(
        ...     balance=50,
        ...     required_amount=100
        ... )
    """

    def __init__(self, balance: float = None, required_amount: float = None, detail: str = None, error_code: str = None):
        if not detail and balance is not None and required_amount is not None:
            detail = f"Insufficient funds. Balance: {balance}, Required: {required_amount}."
        super().__init__(detail=detail or "Insufficient funds.", error_code=error_code or "INSUFFICIENT_FUNDS")


class PaymentFailedException(PaymentRequiredException):
    """Исключение для неудачной оплаты.

    Examples:
        >>> raise PaymentFailedException(
        ...     detail="Payment declined by bank",
        ...     error_code="PAYMENT_FAILED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Payment failed.", error_code=error_code or "PAYMENT_FAILED")


class PaymentProcessingException(PaymentRequiredException):
    """Исключение для ошибки обработки платежа.

    Examples:
        >>> raise PaymentProcessingException(
        ...     detail="Payment gateway timeout",
        ...     error_code="PAYMENT_PROCESSING_ERROR"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Payment processing error.", error_code=error_code or "PAYMENT_PROCESSING_ERROR")


# ============================================================================
# Исключения с HTTP статус-кодом 429 (Too Many Requests) - Лимиты запросов
# ============================================================================

class RateLimitException(AppException):
    """Исключение для превышения лимита запросов.

    Используется когда:
    - Слишком много запросов за короткий период
    - Превышен квота API

    Examples:
        >>> raise RateLimitException(
        ...     detail="Too many requests. Please try again in 60 seconds.",
        ...     error_code="RATE_LIMIT_EXCEEDED"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None, retry_after: int = None):
        super().__init__(detail=detail or "Rate limit exceeded.", error_code=error_code or "RATE_LIMIT_EXCEEDED")
        self.status_code = 429
        self.retry_after = retry_after


# ============================================================================
# Исключения с HTTP статус-кодом 500 (Internal Server Error) - Ошибки сервера
# ============================================================================

class DatabaseException(AppException):
    """Исключение для ошибок базы данных.

    Examples:
        >>> raise DatabaseException(
        ...     detail="Database connection failed",
        ...     error_code="DATABASE_ERROR"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Database error.", error_code=error_code or "DATABASE_ERROR")


class ExternalServiceException(AppException):
    """Исключение для ошибок внешних сервисов.

    Examples:
        >>> raise ExternalServiceException(
        ...     service="payment_gateway",
        ...     detail="Payment gateway unavailable",
        ...     error_code="EXTERNAL_SERVICE_ERROR"
        ... )
    """

    def __init__(self, service: str = None, detail: str = None, error_code: str = None):
        if not detail and service:
            detail = f"{service} is unavailable."
        super().__init__(detail=detail or "External service error.", error_code=error_code or "EXTERNAL_SERVICE_ERROR")


class ConfigurationException(AppException):
    """Исключение для ошибок конфигурации.

    Examples:
        >>> raise ConfigurationException(
        ...     detail="Missing required environment variable",
        ...     error_code="CONFIGURATION_ERROR"
        ... )
    """

    def __init__(self, detail: str = None, error_code: str = None):
        super().__init__(detail=detail or "Configuration error.", error_code=error_code or "CONFIGURATION_ERROR")


# ============================================================================
# Экспорт всех исключений
# ============================================================================

__all__ = [
    # Базовый класс
    "AppException",

    # 400 - Validation errors
    "ValidationException",
    "InvalidInputException",
    "MissingRequiredFieldException",

    # 401 - Authentication errors
    "AuthenticationException",
    "InvalidCredentialsException",
    "TokenExpiredException",
    "InvalidTokenException",
    "TokenRequiredException",

    # 403 - Authorization errors
    "ForbiddenException",
    "InsufficientPermissionsException",
    "UserInactiveException",
    "EmailNotVerifiedException",

    # 404 - Not found
    "NotFoundException",
    "UserNotFoundException",
    "OrderNotFoundException",
    "StudioNotFoundException",
    "PhotographerNotFoundException",
    "RoomNotFoundException",

    # 409 - Conflict
    "ConflictException",
    "EmailAlreadyExistsException",
    "SlotAlreadyBookedException",
    "BookingConflictException",
    "StateTransitionException",

    # 402 - Payment required
    "PaymentRequiredException",
    "InsufficientFundsException",
    "PaymentFailedException",
    "PaymentProcessingException",

    # 429 - Rate limit
    "RateLimitException",

    # 500 - Server errors
    "DatabaseException",
    "ExternalServiceException",
    "ConfigurationException",
]
