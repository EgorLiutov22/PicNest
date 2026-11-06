# ============================================================================
# PicNest Marketplace API - Dockerfile
# ============================================================================
# Multi-stage build для оптимизации размера образа и безопасности
# Stage 1 (builder): установка зависимостей, копирование кода
# Stage 2 (runtime): минимальный образ python:3.11-slim
#
# Автор: PicNest Backend Team
# Дата: 2026-10-21
# ============================================================================

# ============================================================================
# Stage 1: Builder - установка зависимостей и сборка проекта
# ============================================================================

FROM python:3.11-slim as builder

# Устанавливаем переменные окружения для оптимизации Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Устанавливаем системные зависимости для установки некоторых пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем директорию для проекта
WORKDIR /build

# Копируем requirements.txt сначала для кэширования слоев
COPY requirements.txt .

# Устанавливаем Python зависимости в виртуальное окружение
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# === ДОБАВЛЕНО: Обновление pip для корректного разрешения зависимостей ===
RUN pip install --no-cache-dir --upgrade pip

# Устанавливаем зависимости из requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - минимальный образ для запуска приложения
# ============================================================================

FROM python:3.11-slim as runtime

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV="production"

# Создаем non-root user для безопасности
RUN groupadd --gid 1000 appgroup &&     useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Устанавливаем системные зависимости (минимальный набор)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создаем рабочую директорию
WORKDIR /app

# Копируем виртуальное окружение из builder stage
COPY --from=builder /opt/venv /opt/venv

# Копируем код приложения
COPY --chown=appuser:appgroup ./app ./app

# Alembic: конфиг и каталог миграций нужны для `alembic upgrade head`
# в отдельном one-shot контейнере (сервис migrate в docker-compose.prod.yml).
COPY --chown=appuser:appgroup ./alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup ./alembic ./alembic

# Так как WORKDIR=/app, мы копируем main.py из корня хоста в /app/main.py
# COPY --chown=appuser:appgroup ./main.py ./main.py

# Устанавливаем права на файлы (только для чтения)
RUN chmod -R 550 /app && \
    chown -R appuser:appgroup /app



# Создаем директорию для логов и данных
RUN mkdir -p /app/logs /app/data && chown appuser:appgroup /app/logs /app/data

RUN chmod 750 /app/logs /app/data

# Переключаемся на non-root user
USER appuser

# Открываем порт приложения
EXPOSE 8000

# Health check для проверки работоспособности приложения
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запускаем приложение через uvicorn
# --proxy-headers + --forwarded-allow-ips: приложение стоит за nginx на хосте,
# без этого request.client.host всегда будет адресом docker-шлюза, и rate
# limiting (slowapi key_func=get_remote_address) ограничит всех клиентов как
# одного. "*" безопасен здесь, потому что порт опубликован только на
# 127.0.0.1 — достучаться до контейнера извне, минуя nginx, нельзя.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]

# ============================================================================
# Stage 3 (опционально): Debug - для отладки
# ============================================================================

FROM runtime as debug

# Устанавливаем инструменты отладки
RUN pip install --no-cache-dir ipython pdbpp faulthandler

# Переключаемся на root user для доступа к файлам системы
USER root

# Разрешаем запись в директорию приложения (для отладки)
RUN chmod -R 750 /app

# Возвращаемся на appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
