from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

# Создаем локальный limiter для этого модуля
limiter = Limiter(key_func=get_remote_address)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crud import create_user, get_user_by_email, update_user, get_user_by_id
from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import EmailAlreadyExistsError, InvalidCredentialsError
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User
from app.schemas.token import TokenRefreshRequest, TokenResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse


settings = get_settings()

router = APIRouter(tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")  # Защита от спама регистрации
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Регистрация нового пользователя с проверкой уникальности email и созданием профиля при необходимости."""
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise EmailAlreadyExistsError(email=user_data.email)

    new_user = await create_user(db=db, user_create=user_data)

    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        phone=new_user.phone,
        role=new_user.role,
        status="pending_verification",
        city=new_user.city or "",
        timezone=new_user.timezone or "Europe/Moscow",
        is_active=True,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")  # Защита от brute-force атак
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    """Аутентификация пользователя по email и паролю с выдачей JWT токенов.
    
    Логгирует успешные и неудачные попытки входа для мониторинга безопасности.
    """
    from app.core.logging import get_logger
    
    logger = get_logger()
    request_id = getattr(request.state, "request_id", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    
    form_data = await request.form()
    username = str(form_data.get("username", ""))
    password = str(form_data.get("password", ""))
    
    # Логируем попытку входа (без пароля)
    logger.info(
        "Login attempt",
        endpoint="/api/v1/auth/login",
        request_id=request_id,
        client_ip=client_ip,
        username=username,
    )

    user = await get_user_by_email(db, username)
    if not user or not verify_password(password, user.hashed_password):
        logger.warning(
            "Login failed - invalid credentials",
            endpoint="/api/v1/auth/login",
            request_id=request_id,
            client_ip=client_ip,
            username=username,
        )
        raise InvalidCredentialsError()
    
    # Успешный вход
    logger.info(
        "Login successful",
        endpoint="/api/v1/auth/login",
        request_id=request_id,
        client_ip=client_ip,
        user_id=user.id,
        username=username,
    )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    access_token = create_access_token(
        data={"user_id": user.id, "role": user.role},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(
        data={"user_id": user.id},
        expires_delta=refresh_token_expires,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")  # Защита от злоупотреблений обновлением токенов
async def refresh_token(token_data: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    """Обновление access токена с использованием валидного refresh токена."""
    from app.core.exceptions import InvalidTokenException, UserNotFoundException
    
    payload = decode_token(token_data.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise InvalidTokenException(
            detail="Невалидный или просроченный refresh токен",
            error_code="INVALID_REFRESH_TOKEN",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise InvalidTokenException(
            detail="Невалидная структура токена",
            error_code="INVALID_TOKEN_PAYLOAD",
        )

    db_user = await get_user_by_id(db, user_id)
    if not db_user or not db_user.is_active:
        raise UserNotFoundException(
            user_id=user_id,
            detail=f"Пользователь с id={user_id} не найден или деактивирован",
            error_code="USER_NOT_FOUND_OR_INACTIVE",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={"user_id": db_user.id, "role": db_user.role},
        expires_delta=access_token_expires,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=token_data.refresh_token,
        token_type="bearer",
    )


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Получение профиля текущего авторизованного пользователя с полными доменными полями."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        role=current_user.role,
        status=current_user.status,
        city=current_user.city or "",
        timezone=current_user.timezone or "Europe/Moscow",
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Частичное обновление данных профиля текущего пользователя с валидацией email."""
    if user_update.email and user_update.email != current_user.email:
        existing_user = await get_user_by_email(db, user_update.email)
        if existing_user and existing_user.id != current_user.id:
            raise EmailAlreadyExistsError(email=user_update.email)

    updated_user = await update_user(
        db=db,
        user_id=current_user.id,
        user_update=user_update,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        first_name=updated_user.first_name,
        last_name=updated_user.last_name,
        phone=updated_user.phone,
        role=updated_user.role,
        status=updated_user.status,
        city=updated_user.city or "",
        timezone=updated_user.timezone or "Europe/Moscow",
        is_active=updated_user.is_active,
        created_at=updated_user.created_at,
        updated_at=updated_user.updated_at,
    )