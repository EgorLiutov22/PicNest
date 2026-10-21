# Интеграция Sentry для мониторинга ошибок

## Обзор

Sentry — это сервис для отслеживания ошибок в реальном времени, который помогает:
- **Обнаруживать ошибки** немедленно после их возникновения
- **Отслеживать производительность** приложения через транзакции и профилирование
- **Фильтровать чувствительные данные** (PII) перед отправкой
- **Классифицировать ошибки** по severity, environment, release

---

## Установка и настройка

### 1. Регистрация в Sentry

1. Перейдите на [https://sentry.io/](https://sentry.io/)
2. Создайте аккаунт (бесплатный план поддерживает до 10k ошибок/месяц)
3. Создайте новый проект для вашего приложения PicNest
4. Выберите Python как язык проекта
5. Получите **DSN (Data Source Name)** — строка вида:

```
https://<public_key>@o<org_id>.ingest.sentry.io/<project_id>
```

### 2. Настройка переменных окружения

Добавьте `SENTRY_DSN` в ваш `.env` файл:

```bash
# В файле .env
SENTRY_DSN=https://abc123@o456789.ingest.sentry.io/123456
ENVIRONMENT=production  # development или production
DEBUG=false
```

**Важно:** Никогда не коммитьте `.env` файл с реальными DSN в Git!

### 3. Установка зависимостей

```bash
pip install sentry-sdk>=1.39.0
```

---

## Конфигурация Sentry

### Автоматическая инициализация

Sentry автоматически инициализируется при запуске приложения если `SENTRY_DSN` указан:

```python
# app/main.py
@app.on_event("startup")
async def startup():
    settings = get_settings()
    setup_sentry(settings)  # Инициализация Sentry
    ...
```

### Параметры конфигурации

| Параметр | Значение (production) | Значение (development) | Описание |
|----------|----------------------|------------------------|----------|
| `traces_sample_rate` | 0.1 (10%) | 1.0 (100%) | Процент транзакций для профилирования |
| `profiles_sample_rate` | 0.1 (10%) | 1.0 (100%) | Процент профилей производительности |
| `environment` | production | development | Окружение приложения |
| `release` | "1.0.0" | "1.0.0-development" | Версия приложения |

---

## Автоматическое отслеживание ошибок

### FastAPI интеграция

Сенсор автоматически отслеживает:
- Все HTTP запросы и ответы
- Исключения в endpoint'ах
- Ошибки валидации данных
- Время выполнения запросов

**Пример:** При ошибке в `/api/v1/orders` Sentry покажет:
```
Traceback (most recent call last):
  File "app/routers/orders/router.py", line 234, in create_order
    order = await OrderService.create_order(...)
  File "app/services/orders/services.py", line 456, in create_order
    raise SlotConflictError("Слот занят")

SlotConflictError: Слот занят при бронировании для ID=123
```

### Логи с контекстом

Все логи из `structlog` автоматически обогащаются информацией о транзакции:
- Request ID (UUID)
- User ID (если авторизован)
- Endpoint и метод HTTP
- Время выполнения запроса

---

## Ручное отслеживание ошибок

### Отслеживание исключений вручную

```python
from app.core.logging import get_logger
import sentry_sdk

logger = get_logger()

try:
    result = some_operation_that_might_fail()
except Exception as e:
    # Локально логируем
    logger.error("Ошибка операции", error=str(e), exc_info=True)
    
    # Отправляем в Sentry с контекстом
    with sentry_sdk.configure_scope(scope) as scope:
        scope.set_tag("operation", "user_registration")
        scope.set_user({"id": user_id, "email": email})
        scope.set_extra("details", {"field": value})
    
    # Отправляем событие в Sentry
    sentry_sdk.capture_exception(e)
```

### Отслеживание транзакций вручную

```python
import sentry_sdk

with sentry_sdk.start_transaction(name="order_creation", op="api.post"):
    logger.info("Начало создания заказа")
    
    # Ваша бизнес-логика
    order = await OrderService.create_order(...)
    
logger.info("Заказ успешно создан", order_id=order.id)
```

---

## Фильтрация чувствительных данных

### Автоматическая фильтрация

В приложении настроен фильтр `before_send_transaction_filter` который:
- Удаляет `user.id` из контекста
- Удаляет `user.username` из контекста  
- Удаляет `user.ip_address` из контекста

Это соответствует требованиям GDPR и защиты персональных данных.

### Ручная фильтрация

```python
from sentry_sdk import configure_scope

with configure_scope() as scope:
    # Установите тег для группировки ошибок
    scope.set_tag("error_category", "validation")
    
    # Добавьте дополнительные контексты
    scope.set_context("order_details", {
        "total_price": order.total_price,
        "items_count": len(order.items),
    })
```

---

## Мониторинг производительности

### Просмотр транзакций в Sentry

1. Перейдите в проект Sentry → **Performance**
2. Выберите период времени (последние 30 минут, час, день)
3. Найдите медленные транзакции:
   - Сортировка по длительности выполнения
   - Фильтр по HTTP методам и путям

### Поиск узких мест

Sentry покажет:
- **慢 запросы** (медленные endpoint'ы)
- **SQL запросы** с высокой задержкой
- **Внешние вызовы** (Redis, другие API)
- **Распределение времени выполнения** по фазам

---

## Best Practices

### ✅ Делайте:

1. **Настраивайте `traces_sample_rate`** в зависимости от окружения:
   - Production: 0.1 (10%) — экономия ресурсов
   - Development: 1.0 (100%) — полное покрытие

2. **Используйте release version**:
   ```python
   release="1.0.0-abc123"  # версия + коммит хэш
   ```

3. **Группируйте ошибки** по категориям:
   ```python
   sentry_sdk.set_tag("error_category", "validation")
   sentry_sdk.set_tag("error_category", "database_error")
   ```

4. **Добавляйте контекст**:
   ```python
   with configure_scope() as scope:
       scope.set_context("order", {"id": 123, "total_price": 5000})
   ```

### ❌ Избегайте:

1. ❌ Отправлять PII (personally identifiable information) в Sentry:
   - Пароли
   - Credit card numbers
   - Полные email адреса (если не нужно для отладки)

2. ❌ Использовать `traces_sample_rate=1.0` в продакшене без необходимости

3. ❌ Логируйте чувствительные данные через Sentry:
   ```python
   # НЕ ДЕЛАЙТЕ ТАК
   sentry_sdk.capture_message(f"Password is {password}")  # Пароль!
   ```

---

## Примеры использования

### Пример 1: Отслеживание ошибки валидации

```python
from fastapi import HTTPException
from app.core.logging import get_logger
import sentry_sdk

logger = get_logger()

try:
    order = await OrderService.create_order(...)
except ValueError as e:
    logger.warning("Ошибка валидации данных заказа", error=str(e))
    
    with configure_scope() as scope:
        scope.set_tag("validation_error", str(e)[:50])  # Обрезаем длинный текст
    
    raise HTTPException(status_code=422, detail=str(e))
```

### Пример 2: Отслеживание производительности создания заказа

```python
from fastapi import Request
import sentry_sdk

@app.post("/orders")
async def create_order(request: Request, order_data: OrderCreate):
    with sentry_sdk.start_transaction(
        name="create_order",
        op="api.post"
    ) as transaction:
        logger = get_logger()
        logger.info("Начало создания заказа", request_id=request.state.request_id)
        
        # Операция с измерением времени
        order = await OrderService.create_order(...)
        
        transaction.set_tag("order_type", str(order.order_type))
        transaction.set_data("total_price", float(order.total_price))
    
    return {"order_id": order.id}
```

### Пример 3: Отслеживание ошибки базы данных

```python
from sqlalchemy.exc import SQLAlchemyError
import sentry_sdk

try:
    await db.execute(query)
except SQLAlchemyError as e:
    logger.error("Ошибка выполнения SQL запроса", error=str(e), exc_info=True)
    
    with configure_scope() as scope:
        scope.set_tag("database_error_type", type(e).__name__)
        scope.set_tag("sql_query_hash", hash(str(query)))  # Для группировки
    
    sentry_sdk.capture_exception()
    
    raise HTTPException(status_code=500, detail="Ошибка базы данных")
```

---

## Отчетность и алертинг

### Настройка алертов в Sentry

1. Перейдите в **Project Settings** → **Alerts**
2. Создайте новые правила алертинга:
   - **Error rate spike**: > 10 ошибок/минуту
   - **Performance degradation**: Среднее время выполнения > 5 секунд
   - **Transaction failure**: > 5% транзакций завершаются с ошибкой

### Экспорт данных

Sentry позволяет экспортировать данные для дальнейшей аналитики:
- CSV отчеты по ошибкам
- JSON экспорт транзакций
- Интеграция с Slack, Email, PagerDuty

---

## Отладка и тестирование интеграции

### Проверка работы Sentry

```python
import sentry_sdk

# Тестовая отправка события
sentry_sdk.capture_message("Test error from PicNest")  # Для проверки
```

После запуска приложения проверьте в Sentry:
1. Проект → **Issues** — должно появиться тестовое событие
2. Проект → **Performance** — должны быть транзакции

### Локальное тестирование

Для локального тестирования настройте `SENTRY_DSN` на тестовый проект или используйте `debug=True`:

```bash
# .env.local
ENVIRONMENT=development
DEBUG=true
SENTRY_DSN=https://test@test.ingest.sentry.io/123  # Тестовый DSN
```

---

## Ссылки и ресурсы

- [Официальная документация Sentry](https://docs.sentry.io/)
- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [Интеграция с FastAPI](https://docs.sentry.io/platforms/python/guides/fastapi/)
- [Best Practices для PII](https://develop.sentry.dev/sdk/data-handling/#pii)

---

**Автор:** PicNest Backend Team  
**Дата:** 2026-10-20  
**Версия:** 1.0.0
