# PicNest Marketplace API

RESTful API для маркетплейса фотостудий и фотографов на FastAPI с управлением расписанием, бронированием и системой отзывов.

## 📋 Содержание

- [Функционал](#функционал)
- [Требования](#требования)
- [Установка](#установка)
- [Настройка окружения](#настройка-окружения)
- [Запуск](#запуск)
- [Структура проекта](#структура-проекта)
- [API Эндпоинты](#api-эндпоинты)
  - [Аутентификация](#аутентификация)
  - [Управление расписанием](#управление-расписанием)
  - [Фотостудии и залы](#фотостудии-и-залы)
  - [Бронирования](#бронирования)
  - [Отзывы](#отзывы)
- [Документация API](#документация-api)
- [Примеры запросов](#примеры-запросов)
- [Поддержка](#поддержка)

## 🎯 Функционал

### Аутентификация и авторизация
- JWT токены (access + refresh)
- Role-Based Access Control (RBAC) с ролями: photographer, studio, admin
- Безопасное хранение паролей (bcrypt)

### Управление расписанием
- **Недельные шаблоны** - регулярное рабочее время по дням недели
- **Исключения из расписания** - назначение выходных дней или кастомного времени для конкретных дат
- **Блокировки слотов** - ручная блокировка периодов для предотвращения двойного бронирования

### Фотостудии и залы
- Профили фотостудий с детальной информацией
- Управление залами (комнатами) студий
- Параметры оборудования и технические характеристики

### Бронирования
- Создание и управление заказами
- Поддержка разных типов заказов
- Интеграция с платежной системой

### Отзывы и рейтинги
- Система отзывов для фотографов и студий
- Расчет рейтингов на основе оценок пользователей

## 📦 Требования

- Python 3.11+
- PostgreSQL 14+
- FastAPI 0.104.0+
- SQLAlchemy 2.0 (async)
- Pydantic v2
- python-jose для JWT токенов
- passlib для хеширования паролей

## 🚀 Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/picnest/picnest.git
cd PicNest

# Установите зависимости
pip install -r requirements.txt
```

## ⚙️ Настройка окружения

Скопируйте `.env.example` в `.env` и настройте переменные:

```bash
cp .env.example .env
```

Редактируйте следующие параметры в `.env`:

| Параметр | Описание | Пример значения |
|----------|----------|-----------------|
| `DATABASE_URL` | Строка подключения к PostgreSQL | `postgresql+asyncpg://user:pass@localhost/picnest` |
| `SECRET_KEY` | Секретный ключ для подписи JWT (минимум 32 символа) | `your-secret-key-minimum-32-chars` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Срок жизни access токена (по умолчанию: 30 минут) | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Срок жизни refresh токена (по умолчанию: 7 дней) | `7` |

## 🏃 Запуск

```bash
# Запуск с uvicorn (рекомендуется для разработки)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Или напрямую через uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Запуск в production режиме с множественными workers
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000
```

## 📁 Структура проекта

```
PicNest/
├── app/
│   ├── core/                    # Ядро приложения
│   │   ├── config.py           # Конфигурация и settings
│   │   ├── db.py              # Настройка async SQLAlchemy
│   │   ├── security.py        # Хеширование паролей и JWT токены
│   │   ├── crud.py            # CRUD операции с базой данных
│   │   ├── dependencies.py    # Зависимости FastAPI (DI)
│   │   ├── exceptions.py      # Кастомные исключения
│   │   └── migrations/        # Скрипты миграций БД
│   │       └── add_schedule_block.py
│   ├── models/                 # SQLAlchemy ORM модели
│   │   ├── base.py           # Базовый класс для моделей
│   │   ├── user.py           # Модель пользователя
│   │   ├── photographerprofile.py
│   │   ├── studioprofile.py
│   │   ├── studioroom.py
│   │   ├── schedule.py       # Модели расписания (новые!)
│   │   └── ...               # Остальные модели
│   ├── schemas/                # Pydantic схемы валидации
│   │   ├── token.py          # Схемы токенов
│   │   ├── user.py           # Схемы пользователя
│   │   └── schedule/         # Схемы расписания (новые!)
│   │       └── schemas.py
│   ├── services/               # Бизнес-логика
│   │   └── schedule/         # Сервисы расписания (новые!)
│   │       └── services.py
│   ├── routers/                # API endpoints
│   │   ├── auth.py           # Роуты аутентификации
│   │   └── schedule/         # Роуты расписания (новые!)
│   │       └── router.py
│   └── main.py                 # Точка входа FastAPI
├── docs/                       # Документация API
│   ├── schedule_management.md  # Документация модуля расписания
│   └── schedule_api.md         # Полная спецификация API
├── .env.example                # Шаблон конфигурации
├── requirements.txt            # Зависимости проекта
└── README.md                   # Этот файл
```

## 🔗 API Эндпоинты

### Аутентификация

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/auth/register` | Регистрация нового пользователя |
| `POST` | `/api/v1/auth/login` | Вход по email и паролю |
| `POST` | `/api/v1/auth/refresh` | Обновление access токена через refresh токен |
| `GET`  | `/api/v1/auth/users/me` | Профиль текущего пользователя (требуется авторизация) |
| `PATCH` | `/api/v1/auth/users/me` | Обновление профиля текущего пользователя |

### Управление расписанием 📅

#### Шаблоны расписания (Weekly Templates)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/templates` | Создать недельный шаблон |
| `GET`  | `/api/v1/schedules/templates` | Получить список шаблонов (с пагинацией) |
| `GET`  | `/api/v1/schedules/templates/{id}` | Получить шаблон по ID |
| `PUT`  | `/api/v1/schedules/templates/{id}` | Обновить шаблон |
| `DELETE` | `/api/v1/schedules/templates/{id}` | Удалить шаблон |
| `POST` | `/api/v1/schedules/templates/bulk` | Массовое создание шаблонов |

#### Исключения из расписания (Exceptions)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/exceptions` | Создать исключение (выходной/кастомное время) |
| `GET`  | `/api/v1/schedules/exceptions` | Получить список исключений |
| `GET`  | `/api/v1/schedules/exceptions/{id}` | Получить исключение по ID |
| `PUT`  | `/api/v1/schedules/exceptions/{id}` | Обновить исключение |
| `DELETE` | `/api/v1/schedules/exceptions/{id}` | Удалить исключение |

#### Блокировки слотов (Blocks)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/blocks` | Создать блокировку слота |
| `GET`  | `/api/v1/schedules/blocks` | Получить список блокировок |
| `GET`  | `/api/v1/schedules/blocks/{id}` | Получить блокировку по ID |
| `DELETE` | `/api/v1/schedules/blocks/{id}` | Разблокировать слот |

**Подробная документация API расписания:** [docs/schedule_api.md](docs/schedule_api.md)

### Фотостудии и залы (Фото для реализации)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `GET`  | `/api/v1/studios` | Получить список фотостудий |
| `GET`  | `/api/v1/studios/{id}` | Получить детали студии |
| `POST` | `/api/v1/rooms` | Создать зал для студии |
| `GET`  | `/api/v1/rooms` | Получить список залов |

### Бронирования (Фото для реализации)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/orders` | Создать заказ на бронирование |
| `GET`  | `/api/v1/orders` | Получить список заказов пользователя |
| `PUT`  | `/api/v1/orders/{id}` | Обновить статус заказа |

### Отзывы (Фото для реализации)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/reviews` | Создать отзыв |
| `GET`  | `/api/v1/reviews` | Получить отзывы для фотографа/студии |

## 📚 Документация API

- [Модуль управления расписанием](docs/schedule_management.md) - Полная документация по модулю расписания
- [API спецификация](docs/schedule_api.md) - Детальная спецификация всех endpoints с примерами запросов/ответов

## 💡 Примеры запросов

### Регистрация нового пользователя

```bash
curl -X POST https://picnest.ru/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "photographer@example.com",
    "password": "secure_password_123",
    "first_name": "Иван",
    "last_name": "Иванов",
    "phone": "+79001234567",
    "role": "photographer",
    "city": "Москва",
    "timezone": "Europe/Moscow"
  }'
```

### Вход в систему и получение токена

```bash
curl -X POST https://picnest.ru/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=photographer@example.com&password=secure_password_123"
```

### Создание недельного шаблона расписания (фотографу)

```bash
curl -X POST https://picnest.ru/api/v1/schedules/templates \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": 1,
    "owner_type": "photographer",
    "day_of_week": 1,
    "start_time": "09:00:00",
    "end_time": "18:00:00"
  }'
```

### Создание исключения (выходной день)

```bash
curl -X POST https://picnest.ru/api/v1/schedules/exceptions \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": 1,
    "owner_type": "photographer",
    "date": "2024-12-31",
    "is_day_off": true
  }'
```

### Блокировка слота (для зала студии)

```bash
curl -X POST https://picnest.ru/api/v1/schedules/blocks \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": 5,
    "owner_type": "room",
    "start_datetime": "2025-01-05",
    "end_datetime": "2025-01-10",
    "reason": "Ремонт освещения"
  }'
```

## 🛠 Поддержка

При возникновении проблем или вопросов:

- **GitHub Issues:** [github.com/picnest/picnest/issues](https://github.com/picnest/picnest/issues)
- **Документация:** [docs/](docs/)


---

**Версия API:** 1.0.0  
**Последнее обновление:** Октябрь 2026  

