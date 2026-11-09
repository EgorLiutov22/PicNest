"""
Демо-каталог: две студии с залами, два фотографа с услугами, график у всех.

Запуск внутри контейнера (нужен DATABASE_URL и полный пакет приложения):
    python /tmp/seed_demo.py

Идемпотентен: повторный запуск обновляет существующие записи по email,
а не плодит дубли. Пароль демо-аккаунтов — Demo12345.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import time
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.db import async_session_maker
from app.core.security import get_password_hash
from app.models.photographerprofile import PhotographerProfile
from app.models.photographerservice import PhotographerService
from app.models.studioprofile import StudioProfile
from app.models.studioroom import StudioRoom
from app.models.user import User
from app.services.schedule.services import ScheduleTemplateService

PASSWORD = "Demo12345"

STUDIOS = [
    {
        "email": "lumen@picnest.demo",
        "title": "Студия Lumen",
        "description": "Светлая студия в центре с тремя залами и естественным светом",
        "address": "Москва, ул. Большая Новодмитровская, 36",
        "rooms": [
            {
                "name": "Белый зал",
                "description": "Панорамные окна, циклорама, 120 м²",
                "area": 120,
                "ceiling_height": Decimal("4.5"),
                "price_per_hour": Decimal("3500.00"),
                "min_rent_hours": 1,
                # пн-пт 09:00-21:00, сб-вс 11:00-19:00
                "schedule": {
                    1: (time(9), time(21)),
                    2: (time(9), time(21)),
                    3: (time(9), time(21)),
                    4: (time(9), time(21)),
                    5: (time(9), time(21)),
                    6: (time(11), time(19)),
                    7: (time(11), time(19)),
                },
            },
            {
                "name": "Тёмный зал",
                "description": "Чёрные стены, управляемый свет, 60 м²",
                "area": 60,
                "ceiling_height": Decimal("3.8"),
                "price_per_hour": Decimal("2800.00"),
                "min_rent_hours": 2,
                "schedule": {
                    1: (time(10), time(20)),
                    2: (time(10), time(20)),
                    3: (time(10), time(20)),
                    4: (time(10), time(20)),
                    5: (time(10), time(20)),
                },
            },
        ],
    },
    {
        "email": "atelier@picnest.demo",
        "title": "Ателье Север",
        "description": "Камерная студия для портретной и предметной съёмки",
        "address": "Санкт-Петербург, наб. реки Мойки, 12",
        "rooms": [
            {
                "name": "Портретный зал",
                "description": "Мягкий рассеянный свет, зона визажа, 45 м²",
                "area": 45,
                "ceiling_height": Decimal("3.2"),
                "price_per_hour": Decimal("2200.00"),
                "min_rent_hours": 1,
                # ежедневно 10:00-20:00
                "schedule": {
                    d: (time(10), time(20)) for d in range(1, 8)
                },
            },
        ],
    },
]

PHOTOGRAPHERS = [
    {
        "email": "anna@picnest.demo",
        "display_name": "Анна Соколова",
        "bio": "Портретная и свадебная съёмка, 8 лет опыта, работаю с естественным светом",
        "legal_status": "Самозанятая",
        "services": [
            {
                "title": "Портретная съёмка",
                "description": "2 часа в студии, 30 обработанных кадров",
                "duration_minutes": 120,
                "photos_count": 30,
                "delivery_days": 5,
                "price": Decimal("9000.00"),
            },
            {
                "title": "Свадебная съёмка",
                "description": "Полный день, два фотографа",
                "duration_minutes": 480,
                "photos_count": 300,
                "delivery_days": 21,
                "price": Decimal("45000.00"),
            },
        ],
        # пн-пт 09:00-18:00
        "schedule": {
            d: (time(9), time(18)) for d in range(1, 6)
        },
    },
    {
        "email": "dmitry@picnest.demo",
        "display_name": "Дмитрий Орлов",
        "bio": "Съёмка мероприятий, репортаж, работа с постановочным светом",
        "legal_status": "ИП",
        "services": [
            {
                "title": "Репортажная съёмка",
                "description": "3 часа, 150 кадров",
                "duration_minutes": 180,
                "photos_count": 150,
                "delivery_days": 7,
                "price": Decimal("12000.00"),
            },
            {
                "title": "Экспресс-портрет",
                "description": "1 час, 10 кадров",
                "duration_minutes": 60,
                "photos_count": 10,
                "delivery_days": 3,
                "price": Decimal("5000.00"),
            },
        ],
        # вт-сб 12:00-21:00
        "schedule": {
            2: (time(12), time(21)),
            3: (time(12), time(21)),
            4: (time(12), time(21)),
            5: (time(12), time(21)),
            6: (time(12), time(21)),
        },
    },
]


async def _get_or_create_user(db, email: str, role: str, first_name: str, last_name: str):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        import uuid

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            first_name=first_name,
            last_name=last_name,
            role=role,
            status="active",
            city="Москва",
            timezone="Europe/Moscow",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user, True

    user.role = role
    user.status = "active"
    user.is_active = True
    await db.flush()
    return user, False


async def seed_studios(db) -> None:
    for spec in STUDIOS:
        user, created = await _get_or_create_user(
            db, spec["email"], "studio", spec["title"], ""
        )

        result = await db.execute(
            select(StudioProfile).where(StudioProfile.user_id == user.id)
        )
        studio = result.scalar_one_or_none()

        if studio is None:
            studio = StudioProfile(user_id=user.id)
            db.add(studio)

        studio.title = spec["title"]
        studio.description = spec["description"]
        studio.address = spec["address"]
        studio.rating = Decimal("4.70")
        await db.flush()

        for room_spec in spec["rooms"]:
            result = await db.execute(
                select(StudioRoom).where(
                    StudioRoom.studio_id == studio.id,
                    StudioRoom.name == room_spec["name"],
                )
            )
            room = result.scalar_one_or_none()

            if room is None:
                room = StudioRoom(studio_id=studio.id, name=room_spec["name"])
                db.add(room)

            room.description = room_spec["description"]
            room.area = room_spec["area"]
            room.ceiling_height = room_spec["ceiling_height"]
            room.price_per_hour = room_spec["price_per_hour"]
            room.min_rent_hours = room_spec["min_rent_hours"]
            await db.flush()

            # Шаблон через сервис: уникальность дня недели проверяет БД,
            # поэтому повторный засев сначала чистит старые строки.
            from app.models.schedule import ScheduleTemplate

            await db.execute(
                ScheduleTemplate.__table__.delete().where(
                    ScheduleTemplate.room_id == room.id
                )
            )
            for day, (start, end) in room_spec["schedule"].items():
                await ScheduleTemplateService.create_template(
                    db,
                    owner_id=room.id,
                    owner_type="room",
                    day_of_week=day,
                    start_time=start,
                    end_time=end,
                )
            await db.flush()

        status = "создана" if created else "обновлена"
        print(f"  студия {studio.title}: {status}, залов {len(spec['rooms'])}")


async def seed_photographers(db) -> None:
    for spec in PHOTOGRAPHERS:
        user, created = await _get_or_create_user(
            db, spec["email"], "photographer", *spec["display_name"].split(" ", 1)
        )

        result = await db.execute(
            select(PhotographerProfile).where(PhotographerProfile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()

        if profile is None:
            profile = PhotographerProfile(user_id=user.id, display_name=spec["display_name"])
            db.add(profile)

        profile.display_name = spec["display_name"]
        profile.bio = spec["bio"]
        profile.legal_status = spec["legal_status"]
        profile.verification_status = "verified"
        profile.rating = Decimal("4.80")
        await db.flush()

        for service_spec in spec["services"]:
            result = await db.execute(
                select(PhotographerService).where(
                    PhotographerService.photographer_id == profile.id,
                    PhotographerService.title == service_spec["title"],
                )
            )
            service = result.scalar_one_or_none()

            if service is None:
                service = PhotographerService(
                    photographer_id=profile.id, title=service_spec["title"]
                )
                db.add(service)

            service.description = service_spec["description"]
            service.duration_minutes = service_spec["duration_minutes"]
            service.photos_count = service_spec["photos_count"]
            service.delivery_days = service_spec["delivery_days"]
            service.price = service_spec["price"]
            await db.flush()

        from app.models.schedule import ScheduleTemplate

        await db.execute(
            ScheduleTemplate.__table__.delete().where(
                ScheduleTemplate.photographer_id == profile.id
            )
        )
        for day, (start, end) in spec["schedule"].items():
            await ScheduleTemplateService.create_template(
                db,
                owner_id=profile.id,
                owner_type="photographer",
                day_of_week=day,
                start_time=start,
                end_time=end,
            )
        await db.flush()

        status = "создан" if created else "обновлён"
        print(f"  фотограф {profile.display_name}: {status}, услуг {len(spec['services'])}")


async def main() -> None:
    async with async_session_maker() as db:
        print("Студии:")
        await seed_studios(db)
        print("Фотографы:")
        await seed_photographers(db)
        await db.commit()
    print(f"Готово. Пароль демо-аккаунтов: {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
