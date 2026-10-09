# Schedule Management Module - PicNest Marketplace

Модуль управления расписанием для маркетплейса фотостудий и фотографов. Обеспечивает управление рабочим графиком фотографов и залов фотостудий с поддержкой недельных шаблонов, исключений и ручных блокировок временных слотов.

## 📋 Содержание

- [Функционал](#функционал)
- [Архитектура](#архитектура)
- [Модели данных](#модели-данных)
- [REST API Endpoints](#rest-api-endpoints)
- [RBAC и права доступа](#rbac-и-права-доступа)
- [Валидация данных](#валидация-данных)
- [Обработка ошибок](#обработка-ошибок)
- [Использование](#использование)

## 🎯 Функционал

### 1. Управление недельными шаблонами расписания (ScheduleTemplate)

- Создание и редактирование рабочих часов по дням недели
- Поддержка всех дней недели (понедельник = 1, воскресенье = 7)
- Валидация времени начала и окончания работы
- Массовое создание шаблонов для всех дней недели одновременно

### 2. Управление исключениями из расписания (ScheduleException)

- Назначение конкретных дат выходными днями (`is_day_off = true`)
- Установка кастомного времени работы для отдельных дат
- Приоритет исключений над недельным шаблоном для конкретной даты
- Проверка на дубликаты (одна запись на одну дату для одного владельца)

### 3. Ручная блокировка временных слотов (ScheduleBlock)

- Блокировка периодов времени для предотвращения бронирования
- Предотвращение двойного бронирования при сторонних заказах
- Проверка пересечений с существующими блокировками
- Опциональное указание причины блокировки

## 🏗 Архитектура

Модуль построен в соответствии с принципами **Чистой Архитектуры**:

```
┌─────────────────────────────────────────────────────────┐
│                  Presentation Layer                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │           API Endpoints (router.py)               │  │
│  │  - RESTful endpoints с FastAPI                    │  │
│  │  - Валидация через Pydantic v2                    │  │
│  │  - Обработка ошибок и статус-кодов                │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                     Business Layer                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Services (services.py)                  │  │
│  │  - Бизнес-логика и валидация                      │  │
│  │  - RBAC проверки                                   │  │
│  │  - Проверка пересечений                           │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                     Data Layer                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Models (schedule.py)                    │  │
│  │  - SQLAlchemy ORM модели                          │  │
│  │  - Валидация на уровне БД                         │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                  Schema Layer                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │      Pydantic v2 Schemas (schemas.py)             │  │
│  │  - Валидация входных данных                       │  │
│  │  - Формирование ответов                           │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 📊 Модели данных

### ScheduleTemplate (Недельный шаблон)

Определяет регулярное рабочее время по дням недели.

```python
class ScheduleTemplate(Base):
    id: int  # Primary key
    photographer_id: Optional[int]  # FK to photographer_profiles
    room_id: Optional[int]          # FK to studio_rooms
    day_of_week: int               # 1-7 (понедельник-воскресенье)
    start_time: time               # Время начала работы
    end_time: time                 # Время окончания работы
    
    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR "
            "(photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_template_owner"
        ),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="check_day_of_week")
    )
```

### ScheduleException (Исключение из расписания)

Позволяет назначать конкретные даты выходными или кастомным временем.

```python
class ScheduleException(Base):
    id: int                    # Primary key
    photographer_id: Optional[int]  # FK to photographer_profiles
    room_id: Optional[int]          # FK to studio_rooms
    date: date                 # Дата исключения
    is_day_off: bool           # Является ли день выходным
    custom_start_time: Optional[time]  # Кастомное время начала
    custom_end_time: Optional[time]    # Кастомное время окончания
    
    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR "
            "(photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_exception_owner"
        )
    )
```

### ScheduleBlock (Блокировка слота)

Ручная блокировка периода времени для предотвращения бронирования.

```python
class ScheduleBlock(Base):
    id: int                # Primary key
    photographer_id: Optional[int]  # FK to photographer_profiles
    room_id: Optional[int]          # FK to studio_rooms
    start_datetime: date   # Дата начала блокировки
    end_datetime: date     # Дата окончания блокировки
    reason: Optional[str]  # Причина блокировки (до 500 символов)
    
    __table_args__ = (
        CheckConstraint(
            "(photographer_id IS NOT NULL AND room_id IS NULL) OR "
            "(photographer_id IS NULL AND room_id IS NOT NULL)",
            name="check_block_owner"
        )
    )
```

## 🔗 REST API Endpoints

### Шаблоны расписания (Templates)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/templates` | Создать шаблон расписания |
| `GET`  | `/api/v1/schedules/templates` | Получить список шаблонов (с пагинацией) |
| `GET`  | `/api/v1/schedules/templates/{template_id}` | Получить шаблон по ID |
| `PUT`  | `/api/v1/schedules/templates/{template_id}` | Обновить шаблон |
| `DELETE` | `/api/v1/schedules/templates/{template_id}` | Удалить шаблон |
| `POST` | `/api/v1/schedules/templates/bulk` | Массовое создание шаблонов |

### Исключения из расписания (Exceptions)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/exceptions` | Создать исключение |
| `GET`  | `/api/v1/schedules/exceptions` | Получить список исключений |
| `GET`  | `/api/v1/schedules/exceptions/{exception_id}` | Получить исключение по ID |
| `PUT`  | `/api/v1/schedules/exceptions/{exception_id}` | Обновить исключение |
| `DELETE` | `/api/v1/schedules/exceptions/{exception_id}` | Удалить исключение |

### Блокировки слотов (Blocks)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/v1/schedules/blocks` | Создать блокировку |
| `GET`  | `/api/v1/schedules/blocks` | Получить список блокировок |
| `GET`  | `/api/v1/schedules/blocks/{block_id}` | Получить блокировку по ID |
| `DELETE` | `/api/v1/schedules/blocks/{block_id}` | Разблокировать слот |

## 🔐 RBAC и права доступа

### Роли пользователей:

- **photographer** (фотограф) - может управлять только своим расписанием
- **studio** (представитель студии) - может управлять расписанием только своих залов
- **admin** (администратор) - имеет полный доступ ко всем записям

### Правила доступа:

1. **Фотографы:**
   - Могут создавать, обновлять и удалять шаблоны для своего профиля
   - Могут создавать исключения только для своего расписания
   - Могут блокировать слоты только в своём графике

2. **Представители студий:**
   - Могут управлять расписанием только залов своей студии
   - Не имеют доступа к расписанию других студий

3. **Администраторы:**
   - Имеют полный доступ ко всем записям расписания всех фотографов и студий

## ✅ Валидация данных

### На уровне Pydantic v2:

- **Время начала < Время окончания** - строгая проверка для всех временных интервалов
- **День недели в диапазоне 1-7** - валидация через Enum `DayOfWeek`
- **Дата начала < Дата окончания** - для блокировок слотов
- **is_day_off = true** не допускает указания кастомного времени

### На уровне сервисов:

- **Проверка существования владельца** - фотограф или зал должны существовать
- **Проверка прав доступа** - RBAC валидация для каждого запроса
- **Отсутствие пересечений** - блокировки не могут накладываться друг на друга
- **Нет дубликатов** - нельзя создать два исключения на одну дату для одного владельца

## ❌ Обработка ошибок

### Статус-коды HTTP:

| Код | Описание | Когда возникает |
|-----|----------|----------------|
| `400 Bad Request` | Ошибка валидации данных | Некорректное время, день недели вне диапазона, пересечение дат |
| `403 Forbidden` | Отказ в доступе | Попытка редактировать чужое расписание |
| `404 Not Found` | Запись не найдена | Шаблон/исключение/блокировка с указанным ID не существует |
| `409 Conflict` | Конфликт данных | Пересечение блокировок, дублирование исключения на дату |

### Примеры ответов об ошибках:

```json
{
    "detail": "Время начала работы должно быть строго меньше времени окончания"
}

{
    "detail": "Фотограф может редактировать только своё расписание"
}

{
    "detail": "Шаблон расписания с ID 42 не найден"
}

{
    "detail": "Новая блокировка пересекается с существующей блокировкой"
}
```

## 🚀 Использование

### Пример создания недельного шаблона для фотографа:

```python
import requests

# Авторизация и получение токена
login_response = requests.post(
    "http://localhost:8000/api/v1/auth/login",
    json={
        "email": "photographer@example.com",
        "password": "secure_password"
    }
)
token = login_response.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# Создание шаблона расписания для понедельника (day_of_week=1)
template_data = {
    "owner_id": 1,  # ID фотограф профиля
    "owner_type": "photographer",
    "day_of_week": 1,
    "start_time": "09:00:00",
    "end_time": "18:00:00"
}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/templates",
    json=template_data,
    headers=headers
)

print(response.json())  # {"id": 42, "owner_id": 1, ...}
```

### Пример массового создания шаблонов на всю неделю:

```python
templates = [
    {"owner_id": 1, "owner_type": "photographer", "day_of_week": d, 
     "start_time": "09:00:00", "end_time": "18:00:00"}
    for d in range(1, 6)  # Пн-Пт
]

bulk_data = {"templates": templates}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/templates/bulk",
    json=bulk_data,
    headers=headers
)

print(response.json())  
# {"created_count": 5, "failed_templates": []}
```

### Пример создания исключения (выходной день):

```python
exception_data = {
    "owner_id": 1,
    "owner_type": "photographer",
    "date": "2024-12-31",
    "is_day_off": True
}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/exceptions",
    json=exception_data,
    headers=headers
)

print(response.json())  # {"id": 15, "date": "2024-12-31", ...}
```

### Пример блокировки слота:

```python
block_data = {
    "owner_id": 1,
    "owner_type": "photographer",
    "start_datetime": "2024-12-25",
    "end_datetime": "2024-12-26",
    "reason": "Новогодние праздники"
}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/blocks",
    json=block_data,
    headers=headers
)

print(response.json())  # {"id": 7, "start_datetime": "2024-12-25", ...}
```

## 📦 Установка и запуск

### Требования:

- Python 3.11+
- PostgreSQL 14+
- FastAPI с uvicorn
- SQLAlchemy 2.0 (async)
- Pydantic v2

### Установка зависимостей:

```bash
cd PicNest
pip install -r requirements.txt
```

### Запуск миграции для создания таблицы schedule_blocks:

```bash
python -m app.core.migrations.add_schedule_block
```

### Запуск сервера:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📝 Лицензия

PicNest Marketplace © 2024. Все права защищены.

---

**Разработано:** Backend Team, PicNest Marketplace  
**Версия модуля:** 1.0.0  
**Дата создания:** Октябрь 2026
