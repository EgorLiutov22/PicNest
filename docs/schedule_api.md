# PicNest Schedule Management API Documentation

Документация REST API для управления расписанием в маркетплейсе PicNest.

## Базовый URL

```
http://localhost:8000
```

## Авторизация

Все endpoints требуют JWT token в заголовке `Authorization`:

```
Authorization: Bearer <access_token>
```

Получить токен можно через endpoint `/api/v1/auth/login`.

---

## Таблица содержимого

### [Schedule Templates](#schedule-templates)
- [Создать шаблон расписания](#post-apiv1schedules-templates)
- [Получить список шаблонов](#get-apiv1schedules-templates)
- [Получить шаблон по ID](#get-apiv1schedules-templatestemplate_id)
- [Обновить шаблон](#put-apiv1schedules-templatestemplate_id)
- [Удалить шаблон](#delete-apiv1schedules-templatestemplate_id)
- [Массовое создание шаблонов](#post-apiv1schedules-templatesbulk)

### [Schedule Exceptions](#schedule-exceptions)
- [Создать исключение](#post-apiv1schedules-exceptions)
- [Получить список исключений](#get-apiv1schedules-exceptions)
- [Получить исключение по ID](#get-apiv1schedules-exceptionsexception_id)
- [Обновить исключение](#put-apiv1schedules-exceptionsexception_id)
- [Удалить исключение](#delete-apiv1schedules-exceptionsexception_id)

### [Schedule Blocks](#schedule-blocks)
- [Создать блокировку](#post-apiv1schedules-blocks)
- [Получить список блокировок](#get-apiv1schedules-blocks)
- [Получить блокировку по ID](#get-apiv1schedules-blocksblock_id)
- [Разблокировать слот](#delete-apiv1schedules-blocksblock_id)

---

## Schedule Templates

### `POST /api/v1/schedules/templates`

Создаёт новый недельный шаблон расписания.

#### Headers
```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body (ScheduleTemplateCreate)
```json
{
  "owner_id": 1,
  "owner_type": "photographer",
  "day_of_week": 1,
  "start_time": "09:00:00",
  "end_time": "18:00:00"
}
```

**Поля:**
- `owner_id` (int, required): ID владельца (photographer_profile.id или room.id)
- `owner_type` (string, enum): Тип владельца (`photographer` | `room`)
- `day_of_week` (int, 1-7): День недели (1=понедельник, 7=воскресенье)
- `start_time` (time, required): Время начала работы (формат HH:MM:SS)
- `end_time` (time, required): Время окончания работы

#### Response (201 Created)
```json
{
  "id": 42,
  "owner_id": 1,
  "owner_type": "photographer",
  "day_of_week": 1,
  "start_time": "09:00:00",
  "end_time": "18:00:00"
}
```

#### Error Responses
- **400 Bad Request**: Некорректные данные (время окончания <= времени начала)
- **403 Forbidden**: Недостаточно прав для создания шаблона
- **404 Not Found**: Владелец с указанным ID не найден

---

### `GET /api/v1/schedules/templates`

Получает список недельных шаблонов расписания с пагинацией.

#### Headers
```
Authorization: Bearer <token>
```

#### Query Parameters
- `owner_id` (int, optional): Фильтр по ID владельца
- `owner_type` (string, enum, optional): Фильтр по типу владельца (`photographer` | `room`)
- `day_of_week` (int, 1-7, optional): Фильтр по дню недели
- `skip` (int, default: 0): Пропустить N записей
- `limit` (int, max: 1000, default: 100): Максимум записей

#### Response (200 OK)
```json
{
  "templates": [
    {
      "id": 42,
      "owner_id": 1,
      "owner_type": "photographer",
      "day_of_week": 1,
      "start_time": "09:00:00",
      "end_time": "18:00:00"
    }
  ],
  "total": 5,
  "skip": 0,
  "limit": 100
}
```

---

### `GET /api/v1/schedules/templates/{template_id}`

Получает данные конкретного шаблона по ID.

#### Response (200 OK)
```json
{
  "id": 42,
  "owner_id": 1,
  "owner_type": "photographer",
  "day_of_week": 1,
  "start_time": "09:00:00",
  "end_time": "18:00:00"
}
```

#### Error Responses
- **403 Forbidden**: Недостаточно прав для просмотра шаблона
- **404 Not Found**: Шаблон с указанным ID не найден

---

### `PUT /api/v1/schedules/templates/{template_id}`

Обновляет существующий шаблон расписания.

#### Request Body (ScheduleTemplateUpdate)
```json
{
  "day_of_week": 2,
  "start_time": "10:00:00"
}
```

**Поля:** Все поля опциональны, обновляются только указанные.

#### Response (200 OK)
```json
{
  "id": 42,
  "owner_id": 1,
  "owner_type": "photographer",
  "day_of_week": 2,
  "start_time": "10:00:00",
  "end_time": "18:00:00"
}
```

---

### `DELETE /api/v1/schedules/templates/{template_id}`

Удаляет шаблон расписания.

#### Response (200 OK)
```json
{
  "status": "success",
  "message": "Шаблон расписания с ID 42 успешно удалён"
}
```

---

### `POST /api/v1/schedules/templates/bulk`

Массовое создание шаблонов для всех дней недели.

#### Request Body (ScheduleTemplatesBulkCreateRequest)
```json
{
  "templates": [
    {
      "owner_id": 1,
      "owner_type": "photographer",
      "day_of_week": 1,
      "start_time": "09:00:00",
      "end_time": "18:00:00"
    },
    {
      "owner_id": 1,
      "owner_type": "photographer",
      "day_of_week": 2,
      "start_time": "09:00:00",
      "end_time": "18:00:00"
    },
    {
      "owner_id": 1,
      "owner_type": "photographer",
      "day_of_week": 3,
      "start_time": "09:00:00",
      "end_time": "18:00:00"
    }
  ]
}
```

#### Response (201 Created)
```json
{
  "created_count": 3,
  "failed_templates": []
}
```

---

## Schedule Exceptions

### `POST /api/v1/schedules/exceptions`

Создаёт исключение из расписания для конкретной даты.

#### Request Body (ScheduleExceptionCreate)
```json
{
  "owner_id": 1,
  "owner_type": "photographer",
  "date": "2024-12-31",
  "is_day_off": true
}
```

**Поля:**
- `owner_id` (int, required): ID владельца
- `owner_type` (string, enum, required): Тип владельца (`photographer` | `room`)
- `date` (string, date format, required): Дата исключения (YYYY-MM-DD)
- `is_day_off` (boolean, default: false): Является ли день выходным
- `custom_start_time` (time, optional): Кастомное время начала
- `custom_end_time` (time, optional): Кастомное время окончания

**Важно:** При `is_day_off=false` необходимо указать `custom_start_time` и `custom_end_time`.

#### Response (201 Created)
```json
{
  "id": 15,
  "owner_id": 1,
  "owner_type": "photographer",
  "date": "2024-12-31",
  "is_day_off": true,
  "custom_start_time": null,
  "custom_end_time": null
}
```

#### Error Responses
- **409 Conflict**: Уже существует исключение на эту дату для этого владельца

---

### `GET /api/v1/schedules/exceptions`

Получает список исключений из расписания.

#### Query Parameters
- `owner_id` (int, optional): Фильтр по ID владельца
- `owner_type` (string, optional): Фильтр по типу владельца
- `date_from` (string, date format, optional): Дата начала фильтрации
- `date_to` (string, date format, optional): Дата конца фильтрации
- `skip`, `limit`: Пагинация

#### Response (200 OK)
```json
{
  "exceptions": [
    {
      "id": 15,
      "owner_id": 1,
      "owner_type": "photographer",
      "date": "2024-12-31",
      "is_day_off": true,
      "custom_start_time": null,
      "custom_end_time": null
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

---

### `PUT /api/v1/schedules/exceptions/{exception_id}`

Обновляет исключение из расписания.

#### Request Body (ScheduleExceptionUpdate)
```json
{
  "is_day_off": false,
  "custom_start_time": "09:00:00",
  "custom_end_time": "18:00:00"
}
```

---

### `DELETE /api/v1/schedules/exceptions/{exception_id}`

Удаляет исключение из расписания.

#### Response (200 OK)
```json
{
  "status": "success",
  "message": "Исключение из расписания с ID 15 успешно удалено"
}
```

---

## Schedule Blocks

### `POST /api/v1/schedules/blocks`

Создаёт блокировку временного слота для предотвращения бронирования.

#### Request Body (ScheduleBlockCreate)
```json
{
  "owner_id": 1,
  "owner_type": "photographer",
  "start_datetime": "2024-12-25",
  "end_datetime": "2024-12-26",
  "reason": "Новогодние праздники"
}
```

**Поля:**
- `owner_id` (int, required): ID владельца
- `owner_type` (string, enum, required): Тип владельца
- `start_datetime` (date, required): Дата начала блокировки
- `end_datetime` (date, required): Дата окончания блокировки
- `reason` (string, max: 500 chars, optional): Причина блокировки

#### Response (201 Created)
```json
{
  "id": 7,
  "owner_id": 1,
  "owner_type": "photographer",
  "start_datetime": "2024-12-25",
  "end_datetime": "2024-12-26",
  "reason": "Новогодние праздники"
}
```

#### Error Responses
- **409 Conflict**: Пересечение с существующей блокировкой

---

### `GET /api/v1/schedules/blocks`

Получает список блокировок временных слотов.

#### Query Parameters
- `owner_id` (int, optional): Фильтр по ID владельца
- `owner_type` (string, optional): Фильтр по типу владельца
- `date_from`, `date_to`: Фильтры по датам
- `skip`, `limit`: Пагинация

#### Response (200 OK)
```json
{
  "blocks": [
    {
      "id": 7,
      "owner_id": 1,
      "owner_type": "photographer",
      "start_datetime": "2024-12-25",
      "end_datetime": "2024-12-26",
      "reason": "Новогодние праздники"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

---

### `DELETE /api/v1/schedules/blocks/{block_id}`

Разблокирует временной слот (удаляет блокировку).

#### Response (200 OK)
```json
{
  "status": "success",
  "message": "Блокировка слота с ID 7 успешно удалена (слот разблокирован)"
}
```

---

## Обработка ошибок

### Формат ответа об ошибке

Все ошибки возвращаются в формате:

```json
{
    "detail": "<описание ошибки>"
}
```

### Статус-коды

| Код | Описание | Пример сообщения |
|-----|----------|------------------|
| 400 | Bad Request | "Время начала работы должно быть строго меньше времени окончания" |
| 403 | Forbidden | "Фотограф может редактировать только своё расписание" |
| 404 | Not Found | "Шаблон расписания с ID 42 не найден" |
| 409 | Conflict | "Новая блокировка пересекается с существующей блокировкой" |

---

## Примеры использования

### Получить своё недельное расписание:

```python
import requests

token = "your_access_token"
headers = {"Authorization": f"Bearer {token}"}

# Получаем шаблоны для фотографа с ID 123
response = requests.get(
    "http://localhost:8000/api/v1/schedules/templates?owner_id=123&owner_type=photographer",
    headers=headers
)

print(response.json())
```

### Создать выходной на конкретную дату:

```python
exception_data = {
    "owner_id": 123,
    "owner_type": "photographer",
    "date": "2024-12-31",
    "is_day_off": True
}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/exceptions",
    json=exception_data,
    headers=headers
)
```

### Заблокировать слот на время отпуска:

```python
block_data = {
    "owner_id": 456,
    "owner_type": "room",
    "start_datetime": "2025-01-05",
    "end_datetime": "2025-01-10",
    "reason": "Ремонт зала"
}

response = requests.post(
    "http://localhost:8000/api/v1/schedules/blocks",
    json=block_data,
    headers=headers
)
```

---

## Валидация данных

### Правила валидации времени:

- **start_time < end_time** - время начала должно быть строго меньше времени окончания
- Формат времени: `HH:MM:SS` (24-часовой формат)
- Примеры: `"09:00:00"`, `"18:30:00"`

### Правила валидации дней недели:

- Диапазон: 1-7
- mapping:
  - 1 = Понедельник (Monday)
  - 2 = Вторник (Tuesday)
  - 3 = Среда (Wednesday)
  - 4 = Четверг (Thursday)
  - 5 = Пятница (Friday)
  - 6 = Суббота (Saturday)
  - 7 = Воскресенье (Sunday)

### Правила валидации дат:

- **start_datetime < end_datetime** для блокировок слотов
- Формат даты: `YYYY-MM-DD`
- Примеры: `"2024-12-31"`, `"2025-01-01"`

---

## RBAC (Role-Based Access Control)

### Роли пользователей:

| Роль | Права доступа |
|------|---------------|
| **photographer** | Может управлять только своим расписанием |
| **studio** | Может управлять расписанием только своих залов |
| **admin** | Полный доступ ко всем записям |

### Проверка прав:

При каждом запросе система проверяет:
1. Действителен ли JWT token
2. Является ли пользователь активным
3. Имеет ли права на выполнение операции (RBAC)

---

## Частые проблемы и решения

### Проблема: "Время окончания должно быть строго после времени начала"

**Решение:** Убедитесь, что `start_time < end_time`. Например:
- ❌ `"20:00:00"` - `"18:00:00"` (некорректно)
- ✅ `"09:00:00"` - `"18:00:00"` (корректно)

### Проблема: "Новая блокировка пересекается с существующей блокировкой"

**Решение:** Проверьте существующие блокировки для владельца и убедитесь, что новый период не пересекается ни с одним из них. Используйте endpoint `GET /api/v1/schedules/blocks` для просмотра всех блокировок.

### Проблема: "У вас нет прав на просмотр этого шаблона"

**Решение:** Убедитесь, что вы используете правильный owner_id и owner_type, соответствующие вашему профилю пользователя.

---

## Поддержка

При возникновении проблем свяжитесь с командой разработки PicNest через GitHub Issues или email support@picnest.com.

**Версия API:** 1.0.0  
**Последнее обновление:** Октябрь 2026
