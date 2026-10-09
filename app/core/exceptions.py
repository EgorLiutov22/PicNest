from typing import Optional


class AppError(Exception):
    """Базовое исключение для сервиса авторизации."""
    status_code: int = 400
    detail: str = "Internal server error"
    headers: Optional[dict] = None

    def __init__(self, *, status_code: int = 400, detail: str = "Internal server error", headers: Optional[dict] = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class EmailAlreadyExistsError(AppError):
    """Пользователь с данным email уже зарегистрирован."""

    def __init__(self, *, email: str = ""):
        super().__init__(status_code=409, detail=f"Email '{email}' already exists")


class InvalidCredentialsError(AppError):
    """Неверные учетные данные или пароль."""

    def __init__(self, *, headers: dict = None):
        super().__init__(status_code=401, detail="Invalid username or password", headers=headers)


class InvalidTokenError(AppError):
    """Токен невалиден (неверный, просрочен или неверный формат)."""

    def __init__(self, *, detail: str = "Invalid token"):
        super().__init__(status_code=401, detail=detail)


class TokenExpiredError(AppError):
    """Токен просрочен."""

    def __init__(self, *, detail: str = "Token has expired", headers: dict = None):
        super().__init__(status_code=401, detail=detail, headers=headers)


class UserInactiveError(AppError):
    """Пользователь деактивирован."""

    def __init__(self, *, detail: str = "User is inactive"):
        super().__init__(status_code=403, detail=detail)


class InvalidTokenPayloadError(AppError):
    """Токен имеет неверный тип (например, refresh токен передан вместо access)."""

    def __init__(self, *, detail: str = "Invalid token payload", headers: dict = None):
        super().__init__(status_code=401, detail=detail, headers=headers)


class UserStatusError(AppError):
    """Ошибка статуса пользователя (pending_verification или blocked)."""

    def __init__(self, *, status: str = "unknown"):
        super().__init__(status_code=403, detail=f"User status '{status}' does not allow this action")