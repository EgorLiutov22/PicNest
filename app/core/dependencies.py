from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import (
    InvalidTokenError,
    TokenExpiredError,
    UserInactiveError,
    InvalidTokenPayloadError,
)
from app.models.user import User
from app.core.crud import get_user_by_id


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Получает текущего авторизованного пользователя из access токена."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Невозможно валидировать учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    from app.core.security import decode_token
    payload = decode_token(token)
    if payload is None:
        raise InvalidTokenError()

    token_type = payload.get("type")
    if token_type != "access":
        raise InvalidTokenPayloadError()

    user_id: Optional[str] = payload.get("user_id")
    if user_id is None:
        raise InvalidTokenPayloadError()

    db_user = await get_user_by_id(db, user_id)
    if db_user is None:
        raise credentials_exception

    if not db_user.is_active:
        raise UserInactiveError()

    return db_user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Проверяет, что пользователь активен."""
    from app.core.exceptions import UserInactiveError
    if not current_user.is_active:
        raise UserInactiveError()
    return current_user