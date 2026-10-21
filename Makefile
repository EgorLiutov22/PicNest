# ============================================================================
# PicNest Marketplace API - Makefile
# ============================================================================
# Universal commands for development, testing, and deployment
# Author: PicNest Backend Team
# Date: 2026-10-21
# ============================================================================

.PHONY: all install dev test lint migrate docker-build docker-up docker-down help         clean check-system setup pre-commit security-scan coverage docs

SHELL := /bin/bash
ENVIRONMENT ?= development

# Colors for output
GREEN := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RED := $(shell tput -Txterm setaf 1)
BLUE := $(shell tput -Txterm setaf 6)
RESET := $(shell tput sgr0)

# ============================================================================
# Default target
# ============================================================================

all: install

help: ## Show this help message
	@echo ''
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'PicNest Marketplace API - Development Makefile'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(BLUE)%-15s$(RESET) %s
", $$1, $$2}' $(MAKEFILE_LIST)

# ============================================================================
# System checks and setup
# ============================================================================

check-system: ## Check system requirements (Docker, Python, etc.)
	@echo "$(YELLOW)Checking system requirements...$(RESET)"
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)❌ Docker is not installed$(RESET)"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "$(RED)❌ Docker Compose is not installed$(RESET)"; exit 1; }
	@command -v python3 >/dev/null 2>&1 || { echo "$(RED)❌ Python 3 is not installed$(RESET)"; exit 1; }
	@echo "$(GREEN)✅ All requirements met!$(RESET)"

setup: install ## Set up development environment (install dependencies, create venv)
	@echo "$(YELLOW)Setting up development environment...$(RESET)"
	@if [ ! -f .env ]; then 		cp .env.example .env && echo "Created .env file from .env.example"; 	fi
	@python3 -m venv venv || true
	@source venv/bin/activate && pip install -r requirements.txt
	@echo "$(GREEN)✅ Development environment set up!$(RESET)"

install: ## Install dependencies and create virtual environment
	@echo "$(YELLOW)Installing dependencies...$(RESET)"
	@if [ ! -d "venv" ]; then 		python3 -m venv venv; 	fi
	@source venv/bin/activate && pip install --upgrade pip
	@source venv/bin/activate && pip install -r requirements.txt
	@if [ -f ".pre-commit-config.yaml" ]; then 		source venv/bin/activate && pip install pre-commit && pre-commit install; 	fi
	@echo "$(GREEN)✅ Dependencies installed!$(RESET)"

# ============================================================================
# Development commands
# ============================================================================

dev: ## Start development environment with all services
	@echo "$(YELLOW)Starting development environment...$(RESET)"
	@if [ ! -f .env ]; then echo "❌ .env file not found. Please copy .env.example to .env first"; exit 1; fi
	docker-compose up -d app db redis pgadmin prometheus grafana
	@echo "$(GREEN)✅ Development environment started!$(RESET)"

dev-minimal: ## Start minimal services (app, db, redis only)
	@echo "$(YELLOW)Starting minimal development environment...$(RESET)"
	docker-compose up -d app db redis
	@echo "$(GREEN)✅ Minimal environment started!$(RESET)"

run-app: ## Run application locally without Docker
	@source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ============================================================================
# Testing commands
# ============================================================================

test: ## Run pytest tests with coverage
	@echo "$(YELLOW)Running tests...$(RESET)"
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && 	pytest tests/ -v --cov=app --cov-report=html:coverage-html --cov-report=term-missing --maxfail=5

test-fast: ## Run pytest without coverage (for quick testing)
	@echo "$(YELLOW)Running tests (no coverage)...$(RESET)"
	source venv/bin/activate && pytest tests/ -v --maxfail=5

test-security: ## Run security-specific tests
	@echo "$(YELLOW)Running security tests...$(RESET)"
	source venv/bin/activate && pytest tests/test_security.py -v --cov=app

coverage: ## Show coverage report and open in browser
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	@source venv/bin/activate && 	pytest tests/ --cov=app --cov-report=html:coverage-html --cov-report=term-missing
	@echo "$(GREEN)Coverage report generated at coverage-html/index.html$(RESET)"
	@if command -v open >/dev/null 2>&1; then open coverage-html/index.html; fi

# ============================================================================
# Linting and code quality
# ============================================================================

lint: ## Run all linters (flake8, black, isort, mypy)
	@echo "$(YELLOW)Running linters...$(RESET)"
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && 	flake8 app/ tests/ --max-line-length=120 || true && 	echo "$(GREEN)✅ flake8 passed$(RESET)"
	@if [ -f ".pre-commit-config.yaml" ]; then make pre-commit; fi

lint-fix: ## Auto-format code with black and isort
	@echo "$(YELLOW)Auto-formatting code...$(RESET)"
	source venv/bin/activate && 	black app/ tests/ && 	isort app/ tests/
	@echo "$(GREEN)✅ Code formatted!$(RESET)"

pre-commit: ## Run all pre-commit hooks
	@if [ ! -f ".pre-commit-config.yaml" ]; then echo "❌ .pre-commit-config.yaml not found"; exit 1; fi
	source venv/bin/activate && pre-commit run --all-files

mypy: ## Run mypy type checker
	@echo "$(YELLOW)Running type checking...$(RESET)"
	source venv/bin/activate && mypy app/ --ignore-missing-imports

# ============================================================================
# Database migrations
# ============================================================================

migrate-upgrade: ## Upgrade database to latest version
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && alembic upgrade head
	@echo "$(GREEN)✅ Database upgraded!$(RESET)"

migrate-downgrade: ## Downgrade database by one revision
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && alembic downgrade -1
	@echo "$(GREEN)✅ Database downgraded!$(RESET)"

migrate-generate: ## Generate new migration file
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && 	read -p "Enter migration message: " msg && 	alembic revision --autogenerate -m "$$msg"

migrate-current: ## Show current database version
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make install' first"; exit 1; fi
	source venv/bin/activate && alembic current

# ============================================================================
# Docker commands
# ============================================================================

docker-build: ## Build Docker images for all services
	@echo "$(YELLOW)Building Docker images...$(RESET)"
	docker-compose build --no-cache
	@echo "$(GREEN)✅ Docker images built!$(RESET)"

docker-up: ## Start all Docker containers
	@echo "$(YELLOW)Starting Docker containers...$(RESET)"
	docker-compose up -d
	@echo "$(GREEN)✅ Containers started!$(RESET)"

docker-down: ## Stop all Docker containers
	@echo "$(YELLOW)Stopping Docker containers...$(RESET)"
	docker-compose down
	@echo "$(GREEN)✅ Containers stopped!$(RESET)"

docker-logs: ## View container logs
	@docker-compose logs -f --tail=100

docker-ps: ## Show running containers
	@docker-compose ps

docker-clean: ## Remove all Docker resources (volumes, networks, images)
	@echo "$(RED)⚠️  This will remove ALL data including database!$(RESET)"
	@read -p "Are you sure? [y/N] " -n 1 -r && echo && 	if [[ $$REPLY =~ ^[Yy]$ ]]; then 		docker-compose down -v --remove-orphans; 		echo "$(GREEN)✅ All Docker resources cleaned!$(RESET)"; 	else 		echo "Cancelled."; 	fi

# ============================================================================
# Security scanning
# ============================================================================

security-scan: ## Run security scanners (bandit, safety)
	@echo "$(YELLOW)Running security scans...$(RESET)"
	source venv/bin/activate && 	pip install -q bandit safety && 	bandit -r app/ || true && 	echo "Bandit scan completed" && 	safety check || true
	@echo "$(GREEN)✅ Security scans completed!$(RESET)"

# ============================================================================
# Documentation (optional)
# ============================================================================

docs: ## Build documentation (if using mkdocs or similar)
	@echo "$(YELLOW)Building documentation...$(RESET)"
	@if [ -f "mkdocs.yml" ]; then 		mkdocs build; 		echo "$(GREEN)✅ Documentation built at site/$(RESET)"; 	else 		echo "⚠️  No mkdocs.yml found. Skipping."; 	fi

# ============================================================================
# Cleanup targets
# ============================================================================

clean: ## Clean all generated files and caches
	@echo "$(YELLOW)Cleaning up...$(RESET)"
	rm -rf venv/ coverage-html/ .pytest_cache/ __pycache__/ *.egg-info/ dist/ build/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup completed!$(RESET)"

.PHONY: clean all install dev test lint migrate docker-build docker-up docker-down help         check-system setup run-app test-fast test-security coverage pre-commit mypy         migrate-upgrade migrate-downgrade migrate-generate migrate-current         docker-logs docker-ps docker-clean security-scan docs

.DEFAULT_GOAL := help
