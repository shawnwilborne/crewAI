.PHONY: help install dev-install test test-cov format lint type-check clean docker-build docker-up docker-down migrate

# Colors for terminal output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

help: ## Show this help message
	@echo "$(CYAN)Automated Document Processing Workflows$(RESET)"
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	@echo "$(YELLOW)Installing dependencies...$(RESET)"
	pip install -r requirements.txt

dev-install: ## Install development dependencies
	@echo "$(YELLOW)Installing development dependencies...$(RESET)"
	pip install -r requirements.txt
	pip install pre-commit
	pre-commit install

test: ## Run tests
	@echo "$(YELLOW)Running tests...$(RESET)"
	pytest tests/ -v

test-cov: ## Run tests with coverage
	@echo "$(YELLOW)Running tests with coverage...$(RESET)"
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term

format: ## Format code with black and isort
	@echo "$(YELLOW)Formatting code...$(RESET)"
	black app/ tests/ cli.py
	isort app/ tests/ cli.py

lint: ## Run linting checks
	@echo "$(YELLOW)Running linting checks...$(RESET)"
	flake8 app/ tests/ cli.py --max-line-length=88 --extend-ignore=E203,W503
	black --check app/ tests/ cli.py
	isort --check-only app/ tests/ cli.py

type-check: ## Run type checking with mypy
	@echo "$(YELLOW)Running type checks...$(RESET)"
	mypy app/ --ignore-missing-imports

clean: ## Clean temporary files
	@echo "$(YELLOW)Cleaning temporary files...$(RESET)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/
	rm -rf temp/* outputs/* 2>/dev/null || true

docker-build: ## Build Docker image
	@echo "$(YELLOW)Building Docker image...$(RESET)"
	docker-compose build

docker-up: ## Start Docker services
	@echo "$(YELLOW)Starting Docker services...$(RESET)"
	docker-compose up -d

docker-down: ## Stop Docker services
	@echo "$(YELLOW)Stopping Docker services...$(RESET)"
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f

migrate: ## Run database migrations
	@echo "$(YELLOW)Running database migrations...$(RESET)"
	alembic upgrade head

migrate-create: ## Create new migration
	@echo "$(YELLOW)Creating new migration...$(RESET)"
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

run-api: ## Run API server locally
	@echo "$(YELLOW)Starting API server...$(RESET)"
	python -m app.main

run-worker: ## Run Celery worker locally
	@echo "$(YELLOW)Starting Celery worker...$(RESET)"
	celery -A app.worker worker --loglevel=info

run-flower: ## Run Flower monitoring
	@echo "$(YELLOW)Starting Flower monitoring...$(RESET)"
	celery -A app.worker flower --port=5555

cli-help: ## Show CLI help
	python cli.py --help

setup-dev: ## Setup development environment
	@echo "$(YELLOW)Setting up development environment...$(RESET)"
	cp .env.example .env
	make dev-install
	make migrate
	@echo "$(GREEN)Development environment ready!$(RESET)"
	@echo "$(CYAN)Edit .env file with your configuration$(RESET)"

demo: ## Run demo with sample data
	@echo "$(YELLOW)Running demo...$(RESET)"
	python cli.py ingest data/samples/
	@echo "$(GREEN)Demo complete! Check outputs/ directory$(RESET)"

health-check: ## Check system health
	@echo "$(YELLOW)Checking system health...$(RESET)"
	@echo "Python version: $(shell python --version)"
	@echo "Tesseract version: $(shell tesseract --version | head -1)"
	@python -c "import fitz; print(f'PyMuPDF version: {fitz.version[0]}')" 2>/dev/null || echo "PyMuPDF not installed"
	@python -c "import cv2; print(f'OpenCV version: {cv2.__version__}')" 2>/dev/null || echo "OpenCV not installed"

backup-db: ## Backup SQLite database
	@echo "$(YELLOW)Backing up database...$(RESET)"
	cp app.db app.db.backup.$(shell date +%Y%m%d_%H%M%S) 2>/dev/null || echo "No database found"

performance-test: ## Run performance tests
	@echo "$(YELLOW)Running performance tests...$(RESET)"
	pytest tests/performance/ -v --durations=10

security-scan: ## Run security scan
	@echo "$(YELLOW)Running security scan...$(RESET)"
	pip-audit

all-checks: format lint type-check test ## Run all code quality checks
	@echo "$(GREEN)All checks passed!$(RESET)"