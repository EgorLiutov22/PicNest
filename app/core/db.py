import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.pool import NullPool

from .config import get_settings


settings = get_settings()

logger = logging.getLogger(__name__)


postgresql_engine: Optional[AsyncEngine] = None
sqlite_engine: Optional[AsyncEngine] = None
use_postgresql: bool = True


def _check_sync_connection(url: str) -> bool:
    """Синхронная проверка соединения с PostgreSQL."""
    import asyncio

    async def check() -> bool:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
            from sqlalchemy.engine import connect

            engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=1,
                max_overflow=0,
                connect_args={"timeout": 5},
            )

            try:
                async with engine.begin() as conn:
                    await conn.execute("SELECT 1")
                return True
            finally:
                await engine.dispose()
        except Exception:
            return False

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check())
        loop.close()
        return result
    except RuntimeError:
        return False


try:
    connected = _check_sync_connection(settings.DATABASE_URL)

    if connected:
        postgresql_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            connect_args={"timeout": 5},
        )
        logger.info("✅ Successfully connected to PostgreSQL")
    else:
        raise ConnectionError("PostgreSQL connection failed")

except (ConnectionError, Exception) as e:
    logger.warning(f"PostgreSQL unavailable ({e}), falling back to SQLite")
    use_postgresql = False

sqlite_db_url = "sqlite+aiosqlite:///./auth_service.db"
sqlite_engine = create_async_engine(
    sqlite_db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


async_session_maker = async_sessionmaker(
    engine=postgresql_engine if use_postgresql else sqlite_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def get_async_engine() -> AsyncEngine:
    """Получение активного движка базы данных."""
    return postgresql_engine if use_postgresql else sqlite_engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Генератор зависимостей для получения AsyncSession.

    Используется в эндпоинтах FastAPI через Depends().
    Автоматически коммитит изменения при успешном завершении или откатывает при ошибке.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Инициализация базы данных (создание таблиц)."""
    from app.models.base import Base

    engine = get_async_engine()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        if use_postgresql:
            logger.info("✅ Successfully connected to PostgreSQL and initialized tables")
        else:
            logger.warning("⚠️ Using SQLite database (PostgreSQL unavailable)")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_db() -> None:
    """Закрытие соединений с базой данных."""
    if postgresql_engine:
        await postgresql_engine.dispose()
    if sqlite_engine:
        await sqlite_engine.dispose()