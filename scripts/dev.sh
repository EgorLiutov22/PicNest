#!/bin/bash
# ============================================================================
# PicNest Marketplace API - Development Script
# ============================================================================
# Запуск docker-compose для локальной разработки
# Автор: PicNest Backend Team
# Дата: 2026-10-21
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

echo "=================================================="
echo "PicNest Marketplace API - Development Environment"
echo "=================================================="

# Проверка переменных окружения
check_env() {
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo "⚠️  .env file not found. Creating from .env.example..."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo "✅ Created .env file. Please edit it with your settings."
        exit 1
    fi

    # Загрузка переменных окружения
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
}

# Установка зависимостей
install_deps() {
    echo "Installing dependencies..."
    docker-compose pull

    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "$PROJECT_ROOT/venv"
        source "$PROJECT_ROOT/venv/bin/activate"
        pip install -r requirements.txt

        # Установка pre-commit hooks
        if [ -f ".pre-commit-config.yaml" ]; then
            echo "Installing pre-commit hooks..."
            pip install pre-commit
            pre-commit install
        fi
    else
        source "$PROJECT_ROOT/venv/bin/activate"
        echo "Virtual environment already exists."
    fi

    echo "✅ Dependencies installed successfully!"
}

# Запуск сервисов
start_services() {
    echo "Starting services..."

    # Проверяем переменную окружения
    local ENVIRONMENT="${ENVIRONMENT:-development}"

    if [ "$ENVIRONMENT" = "production" ]; then
        echo "⚠️  Production mode detected. Starting minimal services (app, db, redis)..."
        docker-compose up -d app db redis
    else
        echo "Development mode. Starting all services including pgadmin, prometheus, grafana..."

        # Опционально: запуск дополнительных сервисов для development
        local INCLUDE_PGMANAGER="${INCLUDE_PGADMIN:-false}"
        local INCLUDE_MONITORING="${INCLUDE_MONITORING:-true}"

        if [ "$INCLUDE_PGMANAGER" = "true" ]; then
            docker-compose up -d pgadmin
            echo "📊 PgAdmin started at http://localhost:5050"
        fi

        if [ "$INCLUDE_MONITORING" = "true" ]; then
            docker-compose up -d prometheus grafana
            echo "📊 Prometheus started at http://localhost:9090"
            echo "📊 Grafana started at http://localhost:3000 (admin/admin)"
        fi

        docker-compose up -d app db redis
    fi

    echo "✅ Services starting..."

    # Ждем готовности сервисов
    echo "Waiting for services to be healthy..."
    sleep 15

    # Проверка здоровья
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Application is healthy!"
    else
        echo "⚠️  Application health check failed. Check logs with: docker-compose logs app"
    fi

    if docker exec picnest-db pg_isready -U picnest_user -d picnest_db > /dev/null 2>&1; then
        echo "✅ Database is healthy!"
    else
        echo "⚠️  Database health check failed."
    fi

    echo ""
    echo "=================================================="
    echo "Development environment ready!"
    echo "=================================================="
    echo "🌐 API: http://localhost:8000"
    echo "📖 API Docs: http://localhost:8000/docs"
    echo "🔍 Swagger UI: http://localhost:8000/redoc"

    if [ "$INCLUDE_PGMANAGER" = "true" ]; then
        echo "📊 PgAdmin: http://localhost:5050 (admin@example.com / admin)"
    fi

    if docker exec picnest-db pg_isready -U picnest_user -d picnest_db > /dev/null 2>&1; then
        echo "🗄️  PostgreSQL: localhost:5432"
        echo "   User: picnest_user"
        echo "   Password: picnest_pass"
        echo "   Database: picnest_db"
    fi

    if docker exec picnest-redis redis-cli ping > /dev/null 2>&1; then
        echo "📦 Redis: localhost:6379"
    fi

    echo ""
}

# Запуск приложения в режиме разработки
start_app_dev() {
    echo "Starting application in development mode (with auto-reload)..."

    # Создаем .env если нет
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    fi

    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)

    docker-compose up app --build
}

# Запуск тестов
run_tests() {
    echo "Running tests..."

    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        install_deps
    fi

    source "$PROJECT_ROOT/venv/bin/activate"

    export DATABASE_URL="postgresql+asyncpg://picnest_user:picnest_pass@localhost:5432/picnest_db"
    export REDIS_URL="redis://localhost:6379/0"
    export ENVIRONMENT=test

    pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing
}

# Запуск миграций Alembic
run_migrations() {
    echo "Running database migrations..."

    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        install_deps
    fi

    source "$PROJECT_ROOT/venv/bin/activate"

    export DATABASE_URL="postgresql+asyncpg://picnest_user:picnest_pass@localhost:5432/picnest_db"

    # Создание новой миграции (если передан аргумент)
    if [ -n "$1" ]; then
        alembic revision --autogenerate -m "$1"
    else
        alembic upgrade head
    fi

    echo "✅ Migrations completed!"
}

# Просмотр логов
view_logs() {
    local SERVICE="${1:-all}"

    if [ "$SERVICE" = "app" ]; then
        docker-compose logs -f app
    elif [ "$SERVICE" = "db" ]; then
        docker-compose logs -f db
    elif [ "$SERVICE" = "redis" ]; then
        docker-compose logs -f redis
    else
        docker-compose logs -f
    fi
}

# Остановка всех сервисов
stop_services() {
    echo "Stopping all services..."
    docker-compose down
    echo "✅ All services stopped!"
}

# Полная очистка (с удалением volumes)
clean_all() {
    echo "⚠️  This will remove ALL data including database and Redis!"
    read -p "Are you sure? [y/N] " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose down -v --remove-orphans
        rm -rf "$PROJECT_ROOT/venv"
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        echo "✅ All data and environments cleaned!"
    else
        echo "Cancelled."
    fi
}

# Проверка системы
check_system() {
    echo "Checking system requirements..."

    local errors=0

    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker is not installed"
        ((errors++))
    else
        echo "✅ Docker: $(docker --version)"
    fi

    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose is not installed"
        ((errors++))
    else
        echo "✅ Docker Compose: $(docker-compose --version)"
    fi

    # Проверка Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 is not installed"
        ((errors++))
    else
        echo "✅ Python: $(python3 --version)"
    fi

    # Проверка PostgreSQL client (опционально)
    if command -v psql &> /dev/null; then
        echo "✅ PostgreSQL client available"
    else
        echo "⚠️  PostgreSQL client not found (optional)"
    fi

    echo ""

    if [ $errors -gt 0 ]; then
        echo "❌ $errors requirement(s) missing!"
        exit 1
    else
        echo "✅ All requirements met!"
    fi
}

# Показать помощь
show_help() {
    cat << EOF
PicNest Marketplace API - Development Scripts

Usage: dev.sh [command] [options]

Commands:
    start           Start all services (default)
    app             Start application only with auto-reload
    tests           Run pytest tests
    migrations      Run database migrations
    logs [service]  View logs (app, db, redis, or all)
    stop            Stop all services
    clean           Clean all data and environments
    deps            Install dependencies
    check           Check system requirements
    help            Show this help message

Environment Variables:
    ENVIRONMENT     Set environment (development/production) [default: development]
    INCLUDE_PGADMIN Include PgAdmin service [default: false]
    INCLUDE_MONITORING Include Prometheus/Grafana [default: true]

Examples:
    ./dev.sh start              Start all services in development mode
    ./dev.sh app                Start application with auto-reload
    ./ENVIRONMENT=production ./dev.sh start
    INCLUDE_PGADMIN=true ./dev.sh start  # Start with PgAdmin
    ./dev.sh tests              Run pytest tests
    ./dev.sh migrations "add new field" Create migration for new field

EOF
}

# ============================================================================
# Main script logic
# ============================================================================

case "${1:-start}" in
    start)
        check_env
        install_deps
        start_services
        ;;
    app)
        start_app_dev
        ;;
    tests)
        run_tests
        ;;
    migrations)
        run_migrations "$2"
        ;;
    logs)
        view_logs "${2:-all}"
        ;;
    stop)
        stop_services
        ;;
    clean)
        clean_all
        ;;
    deps)
        install_deps
        ;;
    check)
        check_system
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

echo ""
echo "=================================================="
