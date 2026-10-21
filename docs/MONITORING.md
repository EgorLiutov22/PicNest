# Мониторинг и логирование в PicNest Marketplace API

## Обзор

Этот документ описывает интеграцию структурированного логирования, отслеживания ошибок (Sentry) и метрик (Prometheus) для PicNest Marketplace API.

---

## 1. Установка зависимостей

Перед запуском установите необходимые пакеты:

```bash
pip install structlog sentry-sdk prometheus-fastapi-instrumentator
```

Или обновите `requirements.txt` и выполните:

```bash
pip install -r requirements.txt
```

---

## 2. Структурированное логирование (Structlog)

### Конфигурация

Логирование настраивается в [app/core/logging.py](../app/core/logging.py).

**Форматы вывода:**
- **Консольный (разработка)**: Цветной, читаемый формат с индикаторами уровней
- **JSON (продакшен)**: Структурированный JSON для парсинга лог-агрегаторами (ELK, Splunk)

### Контекстные поля

Каждый лог автоматически включает:
- `timestamp`: Время создания лога (ISO 8601)
- `level`: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger_name`: Название модуля/класса
- `request_id`: Уникальный UUID запроса (генерируется middleware)
- `user_id`: ID пользователя (если авторизован)
- `endpoint`: API endpoint
- `method`: HTTP метод

### Использование в коде

```python
from app.core.logging import get_logger, LogContext

# Получение логгера для модуля
logger = get_logger(__name__)

# Базовое логирование
logger.info("Заказ создан", order_id=123, amount=5000)
logger.warning("Возможная проблема", field="phone_number")
logger.error("Ошибка обработки", exc_info=True)

# Добавление контекста для запроса
with LogContext(user_id=user.id, endpoint="/api/v1/orders"):
    # Все логи внутри этого блока будут иметь дополнительные поля
    process_order()
```

### Middleware логирования

Два middleware автоматически логируют все HTTP запросы:

1. **`generate_request_id`**: Генерирует UUID для каждого запроса и передает в контекст логов
2. **`log_requests`**: Логирует метод, путь, статус код и время выполнения

---

## 3. Отслеживание ошибок (Sentry)

### Настройка

1. Создайте проект на [sentry.io](https://sentry.io/)
2. Получите DSN для Python
3. Добавьте в `.env`:

```bash
SENTRY_DSN=https://xxx@sentry.io/yyy
ENVIRONMENT=production  # development, production
DEBUG=false
```

### Конфигурация

Инициализация происходит автоматически при старте приложения:

- Если `SENTRY_DSN` указан → Sentry включен
- Если пустой → Sentry отключен (без ошибок)

**Настройки трассировки:**
- Production: `traces_sample_rate=0.1` (10% транзакций)
- Development: `traces_sample_rate=1.0` (все транзакции)

### Фильтрация PII

Скрипт автоматически фильтрует чувствительные данные перед отправкой в Sentry:
- Удаление `user.id`, `user.username`, `ip_address` из контекста пользователя

---

## 4. Метрики (Prometheus)

### Включение/Отключение

Мониторинг метрик включается через переменную окружения:

```bash
PROMETHEUS_ENABLED=true  # По умолчанию true
```

Для отключения в продакшене:

```bash
PROMETHEUS_ENABLED=false
```

### Эндпоинт метрик

**URL**: `GET /metrics`

**Формат ответа**: `text/plain; version=0.0.4` (формат Prometheus)

**Безопасность**: Доступен только из внутренней сети:
- 127.x.x.x (localhost)
- 192.168.x.x (частная сеть A)
- 10.x.x.x (частная сеть B/C)

### Пример запроса

```bash
# Из внутренней сети
curl http://localhost:8000/metrics

# Или через Prometheus scrape job
scrape_configs:
  - job_name: 'picnest-api'
    static_configs:
      - targets: ['api.internal:8000']
```

### Доступные метрики

#### HTTP запросы (автоматические)
- `http_requests_total` - Counter, labels: method, endpoint, status_code
- `http_request_duration_seconds` - Histogram, labels: method, endpoint, status_code

#### Ошибки
- `errors_total` - Counter, labels: error_type
- `validation_errors_total` - Counter, labels: endpoint, field
- `database_errors_total` - Counter, labels: operation
- `authentication_errors_total` - Counter, labels: reason

#### Бизнес-метрики (заказы)
- `orders_created_total` - Counter, labels: order_type, client_id_hash
- `orders_confirmed_total` - Counter, labels: performer_id_hash
- `orders_cancelled_total` - Counter, labels: reason, refund_percentage

#### Состояние приложения
- `picnest_app_start_time_seconds` - Gauge (Unix timestamp)
- `picnest_active_connections` - Gauge, labels: connection_type

---

## 5. Health Check Endpoint

### URL

**GET `/health`**

### Ответ

```json
{
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2026-10-20T15:30:00Z",
    "database_status": "connected"
}
```

**Статусы:**
- `healthy` - Все компоненты работают нормально
- `degraded` - Есть проблемы (например, БД недоступна)
- `unhealthy` - Критическая ошибка

### Использование в Kubernetes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

---

## 6. Примеры логирования

### Аутентификация (login endpoint)

**Попытка входа:**
```json
{
    "event": "Login attempt",
    "endpoint": "/api/v1/auth/login",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_ip": "192.168.1.100",
    "username": "user@example.com",
    "timestamp": "2026-10-20T15:30:00Z"
}
```

**Неудачный вход:**
```json
{
    "event": "Login failed - invalid credentials",
    "endpoint": "/api/v1/auth/login",
    "request_id": "...",
    "client_ip": "192.168.1.100",
    "username": "user@example.com"
}
```

**Успешный вход:**
```json
{
    "event": "Login successful",
    "endpoint": "/api/v1/auth/login",
    "request_id": "...",
    "client_ip": "192.168.1.100",
    "user_id": 42,
    "username": "user@example.com"
}
```

---

## 7. Локальный запуск для тестирования

### 1. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env с нужными значениями
```

### 2. Запуск сервера

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Проверка health check

```bash
curl http://localhost:8000/health
```

### 4. Просмотр метрик

```bash
# Получение всех метрик
curl http://localhost:8000/metrics

# Фильтрация по prefix (например, только заказы)
curl http://localhost:8000/metrics | grep orders_
```

### 5. Тестирование логирования

В режиме разработки логи выводятся в консоль цветными:

```bash
INFO     Login attempt                   app/routers/auth.py   request_id=abc-123 client_ip=127.0.0.1 username=user@example.com
```

---

## 8. Продакшен развертывание

### Конфигурация для продакшена

`.env.production`:

```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
SENTRY_DSN=https://xxx@sentry.io/yyy
PROMETHEUS_ENABLED=true
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/picnest_db
```

### Логирование в файлы

Для продакшена можно настроить вывод логов в файл через structlog.

### Мониторинг в Grafana

1. Установите Prometheus и Grafana
2. Добавьте datasource типа Prometheus: `http://prometheus:9090`
3. Импортируйте дашборд (ID 12345 - пример)
4. Настройте алерты для критических метрик

---

## 9. Отладка и troubleshooting

### Логи не появляются

**Проверьте:**
- Переменная `ENVIRONMENT` установлена правильно
- Уровень логирования достаточный (`LOG_LEVEL=DEBUG` для разработки)
- Middleware подключены в правильном порядке (в `app/main.py`)

### Sentry не отправляет ошибки

**Проверьте:**
- `SENTRY_DSN` указан в `.env`
- Интернет соединение работает (Sentry требует outbound HTTP)
- Файрвол не блокирует `*.sentry.io`

**Тест:**
```bash
curl -v https://xxx@sentry.io/api/yyy/store
```

### Метрики недоступны

**Проверьте:**
- Переменная `PROMETHEUS_ENABLED=true`
- Запрос из внутренней сети (127.x, 192.168.x, 10.x)
- Prometheus правильно настроен для scrape

---

## 10. Дополнительные ресурсы

- [Structlog documentation](https://www.structlog.org/en/stable/)
- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [Prometheus FastAPI Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- [OpenTelemetry](https://opentelemetry.io/) - для расширенной трассировки

---

## Авторство и обновления

**Автор**: PicNest Backend Team  
**Дата создания**: 2026-10-20  
**Версия документа**: 1.0

### История изменений

| Версия | Дата       | Описание                    |
|--------|------------|-----------------------------|
| 1.0    | 2026-10-20 | Первоначальный релиз        |

---

*Документ поддерживается в актуальном состоянии командой разработки.*
