#!/bin/bash
# ============================================================================
# PicNest Marketplace API - Test Script
# ============================================================================
# Запуск pytest локально с coverage reporting
# Автор: PicNest Backend Team
# Дата: 2026-10-21
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

echo "=================================================="
echo "Running Tests for PicNest Marketplace API"
echo "=================================================="

# Проверка виртуального окружения
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run './dev.sh deps' first to set up the environment."
    exit 1
fi

source "$PROJECT_ROOT/venv/bin/activate"

# Установка переменных окружения
export ENVIRONMENT=test
export DATABASE_URL="postgresql+asyncpg://picnest_user:picnest_pass@localhost:5432/test_db"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="test-secret-key-for-testing-only-change-in-production"

# Установка pytest плагинов если нужно
pip install -q pytest-asyncio httpx pytest-cov 2>/dev/null || true

# Параметры для pytest
PYTEST_ARGS=("$@")

# Запуск тестов
echo "Running pytest with coverage..."
echo ""

pytest     tests/     "${PYTEST_ARGS[@]}"     -v     --cov=app     --cov-report=html:coverage-html     --cov-report=term-missing     --cov-report=xml:coverage.xml     --maxfail=5     --tb=short

echo ""
echo "=================================================="
echo "✅ Tests completed!"
echo "=================================================="
echo "📊 Coverage report available at:"
echo "   HTML: coverage-html/index.html"
echo "   XML:  coverage.xml (for CI/CD)"
echo "=================================================="
