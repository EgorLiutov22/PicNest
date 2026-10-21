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
COPY --chown=appuser:appgroup ./main.py .
COPY --chown=appuser:appgroup ./config.py .

# Устанавливаем права на файлы (только для чтения)
RUN chmod -R 550 /app &&     chown -R appuser:appgroup /app

# Переключаемся на non-root user
USER appuser

# Создаем директорию для логов и данных
RUN mkdir -p /app/logs /app/data && chown appuser:appgroup /app/logs /app/data

# Открываем порт приложения
EXPOSE 8000

# Health check для проверки работоспособности приложения
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запускаем приложение через uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
