# Модуль управления заказами PicNest Marketplace v1.0.0

> Полный, безопасный и готовый к продакшену модуль для создания и управления жизненным циклом заказов маркетплейса фотоуслуг.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-orange)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-yellow)

---

## 📋 Содержание

- [Обзор](# Обзор)
- [Функциональность](# Функциональность)
- [Структура проекта](# структура-проекта)
- [API Endpoints](# api-endpoints)
- [Бизнес-логика](# бизнес-логика)
- [Установка и запуск](# установка-и-запуск)
- [Тестирование](# тестирование)
- [Документация](# документация)
- [Авторы](# авторы)

---

## Обзор

Этот модуль реализует полный жизненный цикл заказов для маркетплейса фотоуслуг **PicNest**. Он поддерживает три типа бронирований:

1. **Только фотограф** (`photographer_only`) — клиент бронирует услуги фотографа
2. **Только зал студии** (`studio_only`) — клиент арендует помещение фотостудии
3. **Комбинированный заказ** (`combined`) — одновременное бронирование фотографа и зала

### Ключевые особенности:

- ✅ **Фиксация данных (снапшот)** — цены, адреса и условия отмены сохраняются на момент бронирования
- ✅ **Атомарная проверка слотов** — исключение двойного бронирования через проверку пересечений
- ✅ **Строгая статусная модель** — контролируемые переходы между состояниями заказа
- ✅ **RBAC авторизация** — разграничение видимости заказов для клиентов и исполнителей
- ✅ **Автоматический расчет возврата** — умный алгоритм расчета суммы возврата при отмене

---

## Функциональность

### 1. Создание заказа с валидацией

```python
POST /api/v1/orders
```

- Валидация временных интервалов (минимум 1 час для фотографа)
- Проверка timezone у datetime полей
- Атомарная проверка отсутствия пересечений с существующими бронями
- Проверка блокировок в расписании и исключений (выходные дни)
- Фиксация цен и условий на момент создания заказа

### 2. Управление статусами заказов

Статусы: `pending_payment` → `confirmed` → `in_progress` → `completed`  
Отмена из любого статуса: `cancelled`

Правила переходов:
- **Исполнитель** подтверждает заказ (`pending_payment` → `confirmed`)
- **Система** переводит в работу после оплаты (`confirmed` → `in_progress`)
- **Клиент** может отменить заказ до завершения работы
- **Система** завершает заказ после выполнения (`in_progress` → `completed`)

### 3. Расчет возврата средств

При отмене заказа автоматически рассчитывается сумма возврата:

| Статус при отмене | Процент возврата | Логика расчета |
|-------------------|------------------|----------------|
| `pending_payment` | 100% | Заказ не подтвержден, полный возврат |
| `confirmed` | 50-80% | Зависит от условий и времени до начала |
| `in_progress` | 0-50% | Зависит от прогресса работы |

### 4. Разграничение видимости (RBAC)

- **Клиенты** видят только свои заказы (`client_id == current_user.id`)
- **Исполнители** видят свои входящие брони (где указаны как фотограф или представитель студии)

---

## Структура проекта

```
app/
├── schemas/orders/              # Pydantic v2 схемы данных
│   ├── __init__.py             # Экспорты схем
│   └── schemas.py              # Модели OrderCreate, OrderItemCreate и др. (531 строка)
│
├── services/orders/             # Бизнес-логика (сервисы)
│   ├── __init__.py             # Экспорты сервисов
│   └── services.py             # OrderService, StatusManagerService (1025 строк)
│
├── routers/orders/              # REST API endpoints
│   ├── __init__.py             # Экспорт роутера
│   └── router.py               # 5 endpoint'ов (711 строк)
│
└── tests/test_orders_module.py # Unit и интеграционные тесты (642 строки)

docs/
├── ORDERS_MODULE.md            # Полная документация API
├── ORDERS_MODULE_SUMMARY.md    # Итоговый обзор модуля
└── README_ORDERS.md            # Этот файл - краткая справка
```

**Общий объем кода:** ~2,900+ строк production-ready кода

---

## API Endpoints

### POST `/api/v1/orders` — Создание заказа

Создает новый заказ с обязательной валидацией и фиксацией данных.

**Request Body:**
```json
{
  "order_type": "photographer_only",
  "items": [
    {
      "photographer_id": 123,
      "photographer_service_id": 456,
      "start_time": "2026-10-15T10:00:00+03:00",
      "end_time": "2026-10-15T14:00:00+03:00"
    }
  ],
  "prepayment_amount": 5000.00,
  "cancellation_conditions": {
    "refund_policy": {"percentage": 80}
  }
}
```

**Responses:**
| Status | Описание |
|--------|----------|
| `201` | Заказ успешно создан |
| `400` | Ошибка валидации данных |
| `403` | Слот заблокирован в расписании |
| `409` | Конфликт слотов (двойное бронирование) |

---

### GET `/api/v1/orders` — Список заказов

Получение списка заказов с фильтрацией и пагинацией.

**Query Parameters:**
- `status` - Фильтр по статусу
- `order_type` - Фильтр по типу заказа
- `start_date`, `end_date` - Временной диапазон
- `skip`, `limit` - Пагинация (0, 20)

---

### GET `/api/v1/orders/{id}` — Детальный просмотр

Получение детальной информации о заказе для участников.

---

### POST `/api/v1/orders/{id}/confirm` — Подтверждение исполнителем

Подтверждает заказ исполнителем (`pending_payment` → `confirmed`).

**Request Body:**
```json
{
  "performer_note": "Готов к съемке, все условия обсудим на месте"
}
```

---

### POST `/api/v1/orders/{id}/cancel` — Отмена с расчетом возврата

Отменяет заказ клиентом или системой.

**Request Body:**
```json
{
  "reason": "Изменились планы на съемку, нужно перенести на другую дату"
}
```

**Response:**
```json
{
  "order_id": 123,
  "status": "cancelled",
  "refund_amount": 4000.00,
  "refund_percentage": 80.0,
  "cancellation_reason": "...",
  "cancelled_at": "2026-10-09T15:30:00+03:00"
}
```

---

## Бизнес-логика

### Проверка доступности слотов (AvailabilityCheckerService)

Перед созданием заказа проверяется три условия:

1. **Отсутствие пересечений с существующими заказами:**
   ```python
   new_start < existing_end AND new_end > existing_start
   ```

2. **Наличие блокировок в расписании (ScheduleBlock):**
   - Ручные блокировки для отпусков, ремонтов и т.д.

3. **Исключения из расписания (ScheduleException):**
   - Выходные дни (`is_day_off = true`)
   - Кастомное время работы

### Снапшот данных при создании заказа

При создании заказа автоматически сохраняются:

| Данные | Поле в OrderItem | Описание |
|--------|------------------|----------|
| Цена за час/фиксированная цена | `fixed_price` | Цена, действовавшая на момент создания |
| Условия отмены | `fixed_conditions` | JSON с адресом, условиями и параметрами |

### Управление статусами (StatusManagerService)

Строгие правила переходов между статусами:

```python
# Валидация перехода
await StatusManagerService.validate_transition(
    current_status=DBOrderStatus.pending_payment,
    target_status=DBOrderStatus.confirmed,
    actor_type="performer",  # "client", "performer", или "system"
)

# Обновление статуса
await StatusManagerService.update_order_status(
    db=session,
    order_id=123,
    new_status=DBOrderStatus.confirmed,
    actor_type="performer",
)

# Расчет возврата
refund_amount, refund_percentage = await StatusManagerService.calculate_refund(...)
```

---

## Установка и запуск

### Требования:

- Python 3.11+
- FastAPI >= 0.100.0
- Pydantic v2 >= 2.0.0
- SQLAlchemy 2.0+ (асинхронная версия)
- PostgreSQL (рекомендуется) или SQLite для тестирования

### Установка зависимостей:

```bash
cd /path/to/picnest
pip install -r requirements.txt
```

### Запуск сервера:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Подключение роутера заказов (в main.py):

```python
from app.routers.orders import router as orders_router

# ... в инициализации FastAPI ...
app.include_router(orders_router, prefix="/api/v1/orders", tags=["Orders Management"])
```

---

## Тестирование

### Запуск unit-тестов:

```bash
pytest app/tests/test_orders_module.py -v --asyncio-mode=auto
```

### Основные категории тестов:

| Категория | Описание |
|-----------|----------|
| `TestOrderSchemaValidation` | Валидация Pydantic схем |
| `TestAvailabilityCheckerService` | Проверка доступности слотов |
| `TestStatusManagerService` | Управление статусами заказов |
| `TestOrderService` | Основной сервис заказов |
| `test_full_order_lifecycle` | Интеграционный тест полного цикла |

### Пример теста:

```python
@pytest.mark.asyncio
async def test_create_order_conflict_slot():
    """Тестирует создание заказа с конфликтом слотов."""
    
    with pytest.raises(SlotConflictError) as exc_info:
        await OrderService.create_order(...)
    
    assert exc_info.value.status_code == 409
```

---

## Документация

Полная документация доступна в следующих файлах:

| Файл | Описание |
|------|----------|
| [ORDERS_MODULE.md](./ORDERS_MODULE.md) | Подробное описание API, бизнес-логики и best practices |
| [ORDERS_MODULE_SUMMARY.md](./ORDERS_MODULE_SUMMARY.md) | Итоговый обзор модуля с архитектурой и примерами |
| [README_ORDERS.md](./README_ORDERS.md) | Этот файл - краткая справка |

---

## Авторы и история версий

**Автор:** PicNest Backend Team  
**Дата создания:** 2026-10-09  
**Версия модуля:** 1.0.0

### История изменений:

| Версия | Дата | Изменения |
|--------|------|-----------|
| 1.0.0 | 2026-10-09 | Первоначальный релиз модуля |

---

## License

Copyright © 2026 PicNest Marketplace. All rights reserved.

---

## Контакты

Для вопросов и предложений обращайтесь:
- **Email:** dev@picnest.ru
- **Slack:** #picnest-backend
