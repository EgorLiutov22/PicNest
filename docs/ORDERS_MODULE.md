# Модуль управления заказами PicNest Marketplace

## Обзор модуля

Этот модуль реализует полный жизненный цикл заказов для маркетплейса фотоуслуг PicNest. Он поддерживает создание, управление и отслеживание трех типов бронирований:

1. **Photographer Only** — только фотограф
2. **Studio Only** — только зал фотостудии  
3. **Combined** — комбинированный заказ (фотограф + зал студии)

## Архитектура

Модуль построен по принципам Чистой Архитектуры и разделен на три слоя:

```
app/
├── schemas/orders/          # Pydantic v2 модели данных
│   ├── __init__.py
│   └── schemas.py
├── services/orders/         # Бизнес-логика (сервисы)
│   ├── __init__.py
│   └── services.py
└── routers/orders/          # REST API endpoints
    ├── __init__.py
    └── router.py
```

### Слои ответственности:

| Слой | Ответственность | Файлы |
|------|----------------|-------|
| **Schemas** | Валидация данных, модели Pydantic v2 | `schemas/orders/schemas.py` |
| **Services** | Бизнес-логика, валидация слотов, управление статусами | `services/orders/services.py` |
| **Routers** | REST API endpoints, обработка HTTP запросов | `routers/orders/router.py` |

## API Endpoints

### 1. POST `/api/v1/orders` — Создание заказа

Создает новый заказ с обязательной валидацией и фиксацией данных (снапшотом).

**Тело запроса:**
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

**Валидация:**
- ✅ Атомарная проверка пересечений с существующими заказами
- ✅ Проверка блокировок в расписании (ScheduleBlock)
- ✅ Проверка исключений из расписания (выходные дни)
- ✅ Фиксация цен и условий на момент создания заказа

**Ответы:**
| Статус | Описание |
|--------|----------|
| `201` | Заказ успешно создан |
| `400` | Ошибка валидации данных |
| `403` | Слот заблокирован в расписании |
| `409` | Конфликт слотов (двойное бронирование) |

---

### 2. GET `/api/v1/orders` — Список заказов

Получение списка заказов с разграничением видимости и пагинацией.

**Параметры запроса:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `status` | string | Фильтр по статусу (pending_payment, confirmed, in_progress, completed, cancelled) |
| `order_type` | string | Фильтр по типу заказа (photographer_only, studio_only, combined) |
| `start_date` | date | Дата начала временного диапазона |
| `end_date` | date | Дата окончания временного диапазона |
| `skip` | int | Количество пропущенных записей (по умолчанию: 0) |
| `limit` | int | Максимальное количество записей (1-100, по умолчанию: 20) |

**Разграничение видимости (RBAC):**
- **Клиент**: видит только свои заказы (`client_id == current_user.id`)
- **Исполнитель**: видит свои входящие брони (где указан как фотограф или представитель студии)

---

### 3. GET `/api/v1/orders/{id}` — Детальный просмотр заказа

Получение детальной информации о заказе для участников.

**Ответ включает:**
- Основная информация: ID, тип, статус, цены, время создания
- Элементы заказа с фиксированными ценами и условиями на момент бронирования
- Информация о фотографе/зале студии
- Условия отмены заказа

---

### 4. POST `/api/v1/orders/{id}/confirm` — Подтверждение исполнителем

Подтверждает заказ исполнителем (фотографом или представителем студии).

**Тело запроса:**
```json
{
  "performer_note": "Готов к съемке, все условия обсудим на месте"
}
```

**Переход статуса:** `pending_payment` → `confirmed`

**Права доступа:** Только исполнитель может подтвердить свой заказ.

---

### 5. POST `/api/v1/orders/{id}/cancel` — Отмена заказа с расчетом возврата

Отменяет заказ клиентом или системой с автоматическим расчетом возврата средств.

**Тело запроса:**
```json
{
  "reason": "Изменились планы на съемку, нужно перенести на другую дату"
}
```

**Расчет возврата:**
| Статус при отмене | Процент возврата | Описание |
|-------------------|------------------|----------|
| `pending_payment` | 100% | Заказ еще не подтвержден |
| `confirmed` | 50-80% | Зависит от условий отмены и времени до начала |
| `in_progress` | 0-50% | Зависит от прогресса работы |

**Ответ включает:**
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

## Статусная модель заказа

Модель статусов строго контролирует переходы между состояниями:

```
pending_payment → confirmed → in_progress → completed
      ↓              ↓            ↓
   cancelled ←───────────────┘
```

### Правила переходов:

| Из статуса | В статус | Кто может инициировать | Описание |
|------------|----------|------------------------|----------|
| `pending_payment` | `confirmed` | Исполнитель | Подтверждение брони |
| `confirmed` | `in_progress` | Система | После оплаты |
| `in_progress` | `completed` | Система | После завершения работы |
| Любой (кроме completed/cancelled) | `cancelled` | Клиент или система | Отмена заказа |

### Запрещенные переходы:
- ❌ Из `completed` или `cancelled` нельзя перейти в другой статус
- ❌ Только исполнитель может подтвердить заказ (`pending_payment` → `confirmed`)
- ❌ Только клиент может отменить свой заказ

---

## Бизнес-логика и валидация

### 1. Проверка доступности слотов (AvailabilityCheckerService)

Перед созданием заказа проверяется:

**a) Отсутствие пересечений с существующими заказами:**
```python
# Два интервала пересекаются если:
new_start < existing_end AND new_end > existing_start
```

**b) Наличие блокировок в расписании (ScheduleBlock):**
- Блокировки создаются вручную для предотвращения бронирования
- Пример: фотограф на отдыхе, ремонт студии

**c) Исключения из расписания (ScheduleException):**
- Выходные дни (`is_day_off = true`)
- Кастомное время работы

### 2. Снапшот данных при создании заказа

При создании заказа фиксируются следующие данные:

| Данные | Описание | Пример |
|--------|----------|--------|
| `fixed_price` | Цена на момент бронирования | `5000.00` |
| `fixed_conditions` | Условия отмены и другая информация | `{ "address": "...", "terms_cancellation": "..." }` |

Это обеспечивает:
- ✅ Стабильность цен независимо от будущих изменений в БД
- ✅ Юридическую фиксацию условий бронирования
- ✅ Возможность аудита истории заказов

---

## Исключения и обработка ошибок

### Кастомные исключения сервисов:

| Исключение | Статус код | Описание |
|------------|------------|----------|
| `OrderValidationError` | 400 | Ошибка валидации данных заказа |
| `SlotConflictError` | 409 | Конфликт временных слотов (двойное бронирование) |
| `ScheduleBlockedException` | 403 | Слот заблокирован в расписании |
| `StatusTransitionNotAllowed` | 400 | Запрещенный переход между статусами |
| `OrderNotFoundError` | 404 | Заказ не найден |
| `OrderForbiddenError` | 403 | Недостаточно прав доступа к заказу |

### Примеры обработки ошибок в API:

**Конфликт слотов (409):**
```json
{
  "detail": {
    "error_type": "slot_conflict",
    "message": "Слот занят другим заказом (ID: 123)",
    "conflicting_order_id": 123
  }
}
```

**Запрещенный переход статуса (400):**
```json
{
  "detail": {
    "error_type": "invalid_transition",
    "message": "Переход из pending_payment в completed запрещен. Разрешены: confirmed"
  }
}
```

---

## Использование модуля

### 1. Создание заказа (клиентом):

```python
from app.schemas.orders.schemas import OrderCreate, OrderItemCreate, OrderTypeEnum
from decimal import Decimal

order_data = OrderCreate(
    order_type=OrderTypeEnum.photographer_only,
    items=[
        OrderItemCreate(
            photographer_id=123,
            photographer_service_id=456,
            start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
            end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
        )
    ],
    prepayment_amount=Decimal("5000.00"),
)

# Вызов через FastAPI endpoint (автоматически валидируется Pydantic)
order = await OrderService.create_order(
    db=session,
    client_id=current_user.id,
    order_data=order_data,
)
```

### 2. Подтверждение заказа (исполнителем):

```python
from app.services.orders.services import StatusManagerService, DBOrderStatus

# Проверка прав и обновление статуса
await StatusManagerService.update_order_status(
    db=session,
    order_id=123,
    new_status=DBOrderStatus.confirmed,
    actor_type="performer",  # "client", "performer", или "system"
)
```

### 3. Расчет возврата средств:

```python
from app.services.orders.services import StatusManagerService

refund_amount, refund_percentage = await StatusManagerService.calculate_refund(
    prepayment_amount=Decimal("5000.00"),
    total_price=Decimal("10000.00"),
    status_at_cancellation=DBOrderStatus.confirmed,
    cancellation_date=datetime.now(),
    created_at=datetime.fromisoformat("2026-10-01T09:00:00+03:00"),
    conditions={"refund_policy": {"percentage": 80}},
)

print(f"Возврат: {refund_amount} ({refund_percentage}%)")
# Вывод: Возврат: 4500.0 (90.0%)
```

---

## Тестирование

### Примеры тестов для модуля заказов:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.db import get_db
from app.services.orders.services import OrderService, SlotConflictError
from app.schemas.orders.schemas import OrderCreate, OrderItemCreate, OrderTypeEnum


@pytest.mark.asyncio
async def test_create_order_valid_slot(db: AsyncSession):
    """Тестирует успешное создание заказа с доступным слотом."""
    
    order_data = OrderCreate(
        order_type=OrderTypeEnum.photographer_only,
        items=[
            OrderItemCreate(
                photographer_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )
        ],
        prepayment_amount=Decimal("5000.00"),
    )
    
    order = await OrderService.create_order(
        db=db,
        client_id=456,
        order_data=order_data,
    )
    
    assert order.order_type == "photographer_only"
    assert order.status.value == "pending_payment"
    assert order.total_price > 0


@pytest.mark.asyncio
async def test_create_order_conflict_slot(db: AsyncSession):
    """Тестирует создание заказа с конфликтом слотов (ожидаемое исключение)."""
    
    # Сначала создаем заказ на тот же временной интервал
    
    order_data = OrderCreate(
        order_type=OrderTypeEnum.photographer_only,
        items=[
            OrderItemCreate(
                photographer_id=123,  # Тот же фотограф
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )
        ],
        prepayment_amount=Decimal("5000.00"),
    )
    
    with pytest.raises(SlotConflictError) as exc_info:
        await OrderService.create_order(
            db=db,
            client_id=456,
            order_data=order_data,
        )
    
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_status_transition_pending_to_confirmed(db: AsyncSession):
    """Тестирует переход статуса pending_payment → confirmed."""
    
    # Создаем заказ в статусе pending_payment
    
    result = await StatusManagerService.update_order_status(
        db=db,
        order_id=123,
        new_status=DBOrderStatus.confirmed,
        actor_type="performer",
    )
    
    assert result.status == DBOrderStatus.confirmed


@pytest.mark.asyncio
async def test_invalid_status_transition(db: AsyncSession):
    """Тестирует запрещенный переход статусов."""
    
    with pytest.raises(StatusTransitionNotAllowed):
        await StatusManagerService.update_order_status(
            db=db,
            order_id=123,
            new_status=DBOrderStatus.completed,  # Нельзя перейти из pending_payment напрямую
            actor_type="system",
        )


@pytest.mark.asyncio
async def test_refund_calculation_pending_payment(db: AsyncSession):
    """Тестирует расчет возврата для статуса pending_payment."""
    
    refund_amount, refund_percentage = await StatusManagerService.calculate_refund(
        prepayment_amount=Decimal("5000.00"),
        total_price=Decimal("10000.00"),
        status_at_cancellation=DBOrderStatus.pending_payment,
        cancellation_date=datetime.now(),
        created_at=datetime.now(),
        conditions={},
    )
    
    assert refund_amount == Decimal("5000.00")  # 100% возврат
    assert refund_percentage == 100.0
```

---

## Best Practices

### ✅ Рекомендации:

1. **Всегда используйте асинхронные сессии БД** (`AsyncSession`)
2. **Проверяйте доступность слотов перед созданием заказа** через `AvailabilityCheckerService`
3. **Фиксируйте все важные данные в снапшоте** (цены, условия, адреса)
4. **Используйте `with_for_update()`** для операций обновления статусов
5. **Обрабатывайте все кастомные исключения** с соответствующими HTTP status codes

### ❌ Избегайте:

1. ❌ Прямого доступа к БД без использования сервисов
2. ❌ Пропуска валидации данных (всегда используйте Pydantic схемы)
3. ❌ Изменения статусов без проверки прав доступа
4. ❌ Создание заказов с невалидными временными интервалами

---

## Зависимости

Модуль использует следующие зависимости:

| Библиотека | Версия | Назначение |
|------------|--------|------------|
| FastAPI | >=0.100.0 | Web framework |
| Pydantic v2 | >=2.0.0 | Валидация данных |
| SQLAlchemy 2.0 | >=2.0.0 | ORM (асинхронная) |
| Python | >=3.11 | Язык программирования |

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

## Связанные документы

- [API Документация PicNest](../README.md)
- [Модель данных заказов](../models/order.py)
- [Сервисы расписания](./SCHEDULE_MODULE.md)
- [Руководство по разработке](../DEVELOPMENT_GUIDE.md)

---

## Контакт

Для вопросов и предложений обращайтесь к команде разработки PicNest.

**Email:** dev@picnest.ru  
**Slack:** #picnest-backend
