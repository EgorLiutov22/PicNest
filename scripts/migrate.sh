#!/bin/bash
# ============================================================================
# PicNest Marketplace API - Migration Script
# ============================================================================
# Запуск Alembic migrations для PostgreSQL базы данных
# Автор: PicNest Backend Team
# Дата: 2026-10-21
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

echo "=================================================="
echo "Database Migrations for PicNest Marketplace API"
echo "=================================================="

# Проверка виртуального окружения
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run './dev.sh deps' first to set up the environment."
    exit 1
fi

source "$PROJECT_ROOT/venv/bin/activate"

# Установка переменных окружения
export DATABASE_URL="postgresql+asyncpg://picnest_user:picnest_pass@localhost:5432/picnest_db"

# Функция для проверки подключения к базе данных
check_database_connection() {
    echo "Checking database connection..."

    if psql "$DATABASE_URL" -c "\q" > /dev/null 2>&1; then
        echo "✅ Database connection successful!"
        return 0
    else
        echo "❌ Failed to connect to database!"
        echo "   DATABASE_URL: $DATABASE_URL"
        echo ""
        echo "Please ensure:"
        echo "1. PostgreSQL is running (docker-compose up -d db)"
        echo "2. Database 'picnest_db' exists"
        echo "3. User credentials are correct in .env file"
        exit 1
    fi
}

# Функция для создания базы данных если не существует
create_database_if_not_exists() {
    local DB_NAME=$(echo "$DATABASE_URL" | sed 's/.*\///')

    if ! psql "postgresql://picnest_user:picnest_pass@localhost:5432/postgres" -c "\l" | grep -q "$DB_NAME"; then
        echo "Creating database '$DB_NAME'..."
        psql "postgresql://picnest_user:picnest_pass@localhost:5432/postgres" -c "CREATE DATABASE $DB_NAME;"
        echo "✅ Database created successfully!"
    else
        echo "Database '$DB_NAME' already exists."
    fi
}

# Показать помощь
show_help() {
    cat << EOF
PicNest Marketplace API - Migration Scripts

Usage: migrate.sh [command] [options]

Commands:
    upgrade HEAD      Upgrade to the latest version (default)
    downgrade N       Downgrade by N revisions
    current           Show current database version
    history           List all available migrations
    stamp VERSION     Stamp database with a specific revision
    generate MESSAGE  Create new migration file

Environment Variables:
    DATABASE_URL      PostgreSQL connection string [default from .env]

Examples:
    ./migrate.sh upgrade HEAD        Upgrade to latest version
    ./migrate.sh downgrade 1         Downgrade by 1 revision
    ./migrate.sh current             Show current version
    ./migrate.sh history             List all migrations
    ./migrate.sh generate "add user field"

EOF
}

# ============================================================================
# Main script logic
# ============================================================================

COMMAND="${1:-upgrade}"
ARG="${2:-HEAD}"

case "$COMMAND" in
    upgrade)
        check_database_connection
        create_database_if_not_exists

        echo ""
        echo "Upgrading database to version $ARG..."

        alembic upgrade "$ARG"

        echo ""
        echo "✅ Database upgraded successfully!"
        ;;

    downgrade)
        check_database_connection

        if [ -z "$ARG" ] || [ "$ARG" = "HEAD" ]; then
            echo "❌ Please specify a revision number to downgrade to."
            show_help
            exit 1
        fi

        echo ""
        echo "Downgrading database by $ARG revisions..."

        alembic downgrade "$ARG"

        echo ""
        echo "✅ Database downgraded successfully!"
        ;;

    current)
        check_database_connection

        echo ""
        echo "Current database version:"
        alembic current
        ;;

    history)
        check_database_connection

        echo ""
        echo "Available migrations:"
        alembic history --verbose
        ;;

    stamp)
        if [ -z "$ARG" ]; then
            echo "❌ Please specify a revision to stamp."
            show_help
            exit 1
        fi

        check_database_connection

        echo ""
        echo "Stamping database with version $ARG..."

        alembic stamp "$ARG"

        echo ""
        echo "✅ Database stamped successfully!"
        ;;

    generate)
        if [ -z "$ARG" ]; then
            echo "❌ Please provide a message for the migration."
            show_help
            exit 1
        fi

        check_database_connection

        echo ""
        echo "Generating new migration..."

        alembic revision --autogenerate -m "$ARG"

        # Открыть файл для редактирования (опционально)
        read -p "Migration file created. Open it for review? [y/N] " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Определить редактор
            EDITOR="${VISUAL:-${EDITOR:-nano}}"
            $EDITOR "$(alembic current --sql | tail -n 1)" 2>/dev/null || true
        fi

        echo ""
        echo "✅ Migration file generated! Review and edit before upgrading."
        ;;

    help|--help|-h)
        show_help
        ;;

    *)
        echo "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac

echo ""
echo "=================================================="
