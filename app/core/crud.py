from uuid import uuid4
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.photographerprofile import PhotographerProfile
from app.models.studioprofile import StudioProfile
from app.schemas.user import UserCreate, UserUpdate
from .security import get_password_hash


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    """Создаёт нового пользователя и автоматически порождает профиль при регистрации.

    При роли photographer создаётся запись в photographer_profiles с status="pending".
    При роли studio создаётся запись в studio_profiles.
    """
    from sqlalchemy import select

    db_user = User(
        id=str(uuid4()),
        email=user_create.email.lower(),
        hashed_password=get_password_hash(user_create.password),
        first_name=user_create.first_name,
        last_name=user_create.last_name,
        phone=user_create.phone,
        role=user_create.role,
        status="pending_verification",
        city=user_create.city,
        timezone=user_create.timezone,
    )

    db.add(db_user)
    await db.flush()  # Получаем id пользователя для создания связанных записей

    # Автоматически создаём связанные профили в зависимости от роли
    if user_create.role == "photographer":
        photographer_profile = PhotographerProfile(
            user_id=db_user.id,
            display_name=f"{user_create.first_name or ''} {user_create.last_name or ''}".strip() or "",
            bio=None,
            avatar_url=None,
            legal_status=None,
            verification_status="pending",
        )
        db.add(photographer_profile)

    elif user_create.role == "studio":
        studio_profile = StudioProfile(
            user_id=db_user.id,
            title=user_create.first_name or "",
            description=None,
            address="",
        )
        db.add(studio_profile)

    await db.commit()
    await db.refresh(db_user)

    return db_user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Получает пользователя по email (с нормализацией к нижнему регистру)."""
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    """Получает пользователя по ID."""
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_with_profile(db: AsyncSession, user_id: str) -> Optional[User]:
    """Получает пользователя вместе с его профилем (для photographer/studio)."""
    from sqlalchemy import select

    db_user = await get_user_by_id(db, user_id)
    if not db_user:
        return None

    if db_user.role == "photographer":
        result = await db.execute(
            select(PhotographerProfile).where(PhotographerProfile.user_id == db_user.id)
        )
        db_user.photographer_profile = result.scalar_one_or_none()

    elif db_user.role == "studio":
        result = await db.execute(
            select(StudioProfile).where(StudioProfile.user_id == db_user.id)
        )
        db_user.studio_profile = result.scalar_one_or_none()

    return db_user


async def update_user(db: AsyncSession, user_id: str, user_update: UserUpdate) -> Optional[User]:
    """Обновляет данные пользователя с валидацией email-уникальности и созданием профилей при смене роли."""
    from sqlalchemy import select

    db_user = await get_user_by_id(db, user_id)
    if not db_user:
        return None

    update_data = user_update.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != db_user.email:
        existing_user = await get_user_by_email(db, update_data["email"])
        if existing_user and existing_user.id != user_id:
            raise ValueError("Email уже занят")
        db_user.email = update_data["email"].lower()

    if "first_name" in update_data:
        db_user.first_name = update_data["first_name"]

    if "last_name" in update_data:
        db_user.last_name = update_data["last_name"]

    if "phone" in update_data:
        db_user.phone = update_data["phone"]

    if "role" in update_data and user_update.role is not None:
        new_role = str(user_update.role)
        existing_profile = await get_user_with_profile(db, user_id)
        has_profile = (hasattr(existing_profile or None, 'photographer_profile') and 
                       getattr(existing_profile, 'photographer_profile', None) is not None or
                       hasattr(existing_profile or None, 'studio_profile') and
                       getattr(existing_profile, 'studio_profile', None) is not None)

        db_user.role = new_role
        
        if new_role in ("photographer", "studio") and not has_profile:
            from sqlalchemy import delete as _del
            
            # Удаляем старый профиль если есть
            if hasattr(db_user, 'photographer_profile') and getattr(db_user, 'photographer_profile', None):
                await db.execute(_del(PhotographerProfile).where(PhotographerProfile.user_id == db_user.id))
            if hasattr(db_user, 'studio_profile') and getattr(db_user, 'studio_profile', None):
                await db.execute(_del(StudioProfile).where(StudioProfile.user_id == db_user.id))

            # Создаём новый профиль
            if new_role == "photographer":
                pp_data = {
                    "user_id": db_user.id,
                    "display_name": f"{db_user.first_name or ''} {db_user.last_name or ''}".strip() or "",
                    "bio": None,
                    "avatar_url": None,
                    "legal_status": None,
                    "verification_status": "pending",
                }
                db.add(PhotographerProfile(**pp_data))

            elif new_role == "studio":
                pp_data = {
                    "user_id": db_user.id,
                    "title": db_user.first_name or "",
                    "description": None,
                    "address": "",
                }
                db.add(StudioProfile(**pp_data))
        else:
            # Удаляем профиль при смене на client или если уже есть
            if hasattr(db_user, 'photographer_profile') and getattr(db_user, 'photographer_profile', None):
                from sqlalchemy import delete as _del
                await db.execute(_del(PhotographerProfile).where(PhotographerProfile.user_id == db_user.id))
            if hasattr(db_user, 'studio_profile') and getattr(db_user, 'studio_profile', None):
                from sqlalchemy import delete as _del
                await db.execute(_del(StudioProfile).where(StudioProfile.user_id == db_user.id))

    if "city" in update_data:
        db_user.city = update_data["city"]

    if "timezone" in update_data:
        db_user.timezone = update_data["timezone"]

    if "password" in update_data and user_update.password:
        db_user.hashed_password = get_password_hash(user_update.password)

    await db.commit()
    await db.refresh(db_user)

    return db_user


async def delete_user(db: AsyncSession, user_id: str):
    """Удаляет пользователя и связанные профили."""
    from sqlalchemy import delete as _del

    db_user = await get_user_by_id(db, user_id)
    if not db_user:
        raise ValueError("Пользователь не найден")

    if hasattr(db_user, 'photographer_profile') and getattr(db_user, 'photographer_profile', None):
        await db.execute(_del(PhotographerProfile).where(PhotographerProfile.user_id == db_user.id))
    if hasattr(db_user, 'studio_profile') and getattr(db_user, 'studio_profile', None):
        await db.execute(_del(StudioProfile).where(StudioProfile.user_id == db_user.id))

    await db.delete(db_user)


async def get_users_by_status(db: AsyncSession, status: str = "active", skip: int = 0, limit: int = 100):
    """Получает список пользователей с фильтрацией по статусу."""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.status == status).offset(skip).limit(limit))
    return list(result.scalars().all())