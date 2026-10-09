"""
Миграция для добавления модели ScheduleBlock в базу данных PicNest.

Этот скрипт создает таблицу schedule_blocks для поддержки блокировок временных слотов,
что позволяет предотвращать двойное бронирование при сторонних заказах.

Запуск:
    python -m app.core.migrations.add_schedule_block
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


async def add_schedule_blocks_table(db: AsyncSession):
    """Добавляет таблицу schedule_blocks в базу данных.
    
    Эта функция должна быть вызвана один раз для инициализации таблицы.
    Таблица содержит информацию о ручных блокировках временных слотов
    фотографов и залов фотостудий.
    """
    
    # Создаём таблицу schedule_blocks с помощью SQLAlchemy Core
    from sqlalchemy import MetaData, Table, Column, Integer, ForeignKey, Date, Text
    
    metadata = MetaData()
    
    schedule_blocks_table = Table(
        "schedule_blocks",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("photographer_id", Integer, ForeignKey("photographer_profiles.id", ondelete="CASCADE")),
        Column("room_id", Integer, ForeignKey("studio_rooms.id", ondelete="CASCADE")),
        Column("start_datetime", Date, nullable=False),
        Column("end_datetime", Date, nullable=False),
        Column("reason", Text(500)),
    )
    
    # Создаём таблицу если её нет
    await db.run_sync(schedule_blocks_table.create)
    
    # Добавляем индекс для быстрого поиска по датам
    from sqlalchemy import Index
    
    index = Index(
        "idx_schedule_blocks_dates",
        "start_datetime",
        "end_datetime"
    )
    
    await db.run_sync(index.create)
    
    # Добавляем ограничение CHECK для обеспечения валидности владельца
    await db.execute(text("""
        ALTER TABLE schedule_blocks
        ADD CONSTRAINT check_block_owner
        CHECK (
            (photographer_id IS NOT NULL AND room_id IS NULL) OR 
            (photographer_id IS NULL AND room_id IS NOT NULL)
        )
    """))
    
    await db.commit()


async def rollback_schedule_blocks_table(db: AsyncSession):
    """Откатывает добавление таблицы schedule_blocks.
    
    Используется для отката миграции если она была применена ошибочно.
    """
    # Удаляем таблицу (если существует)
    from sqlalchemy import text
    
    try:
        await db.execute(text("DROP TABLE IF EXISTS schedule_blocks CASCADE"))
        await db.commit()
    except Exception as e:
        print(f"Ошибка при откате миграции: {e}")


async def main():
    """Точка входа для выполнения миграции."""
    
    # Загрузка конфигурации из .env файла
    from dotenv import load_dotenv
    load_dotenv()
    
    import os
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL не задан в переменных окружения")
    
    # Создаём асинхронный движок SQLAlchemy
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        # Проверяем существует ли уже таблица schedule_blocks
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'schedule_blocks'
            )
        """))
        
        exists = result.scalar()
        
        if exists:
            print("Таблица schedule_blocks уже существует. Пропускаем миграцию.")
            return
        
    # Создаём сессию и выполняем миграцию
    async with sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )() as db:
        
        try:
            await add_schedule_blocks_table(db)
            print("✅ Миграция успешно выполнена! Таблица schedule_blocks создана.")
        except Exception as e:
            print(f"❌ Ошибка при выполнении миграции: {e}")
            raise


if __name__ == "__main__":
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nМиграция отменена пользователем.")
