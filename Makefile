.PHONY: help install install-dev test test-unit test-integration lint format clean run migrate export-openapi

# Default target
help:
	@echo "Available commands:"
	@echo "  make install          - Install production dependencies"
	@echo "  make install-dev      - Install development dependencies"
	@echo "  make test             - Run all tests"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-cov         - Run tests with coverage report"
	@echo "  make lint             - Run code linting (ruff)"
	@echo "  make format           - Format code (black + isort)"
	@echo "  make format-check     - Check code formatting without changes"
	@echo "  make type-check       - Run type checking (mypy)"
	@echo "  make clean            - Remove cache and temporary files"
	@echo "  make run              - Run development server"
	@echo "  make migrate          - Run database migrations"
	@echo "  make export-openapi   - Export OpenAPI specification"
	@echo "  make pre-commit       - Install pre-commit hooks"
	@echo "  make all-checks       - Run all quality checks (format, lint, type, test)"

# Install dependencies
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Testing
test:
	pytest tests/

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "\nCoverage report generated in htmlcov/index.html"

test-watch:
	pytest-watch

# Code quality
lint:
	ruff check src/ tests/

lint-fix:
	ruff check src/ tests/ --fix

format:
	black src/ tests/ scripts/
	isort src/ tests/ scripts/

format-check:
	black src/ tests/ scripts/ --check
	isort src/ tests/ scripts/ --check

type-check:
	mypy src/

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	@echo "Cleaned up cache and temporary files"

# Run application
run:
	uvicorn src.main:app --reload --port 8000

run-prod:
	uvicorn src.main:app --host 0.0.0.0 --port 8000

# Database
migrate:
	python scripts/run_migrations.py

# OpenAPI
export-openapi:
	python scripts/export_openapi_spec.py

# Pre-commit hooks
pre-commit:
	pre-commit install
	@echo "Pre-commit hooks installed"

pre-commit-run:
	pre-commit run --all-files

# Combined checks
all-checks: format-check lint type-check test
	@echo "\n✅ All checks passed!"

# Quick check before commit
check: format lint test-unit
	@echo "\n✅ Quick checks passed!"

# Development setup
setup: install-dev migrate
	@echo "\n✅ Development environment setup complete!"
	@echo "Run 'make run' to start the server"
