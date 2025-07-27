.PHONY: help clean test run migrate setup

help:
	@echo "Available commands:"
	@echo "  make clean       - Remove Python cache files and temporary files"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests"
	@echo "  make test-api    - Run API tests"
	@echo "  make run         - Run development server"
	@echo "  make migrate     - Run database migrations"
	@echo "  make setup       - Initial project setup"
	@echo "  make fixtures    - Load sample data"

clean:
	@echo "Cleaning Python cache files..."
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -not -path "./.venv/*" -delete 2>/dev/null || true
	find . -type f -name "*.log" -not -path "./.venv/*" -delete 2>/dev/null || true
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	@echo "Clean complete!"

test:
	@echo "Running all tests..."
	./scripts/run_tests.sh

test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/unit/

test-api:
	@echo "Running API tests..."
	./scripts/run_tests.sh tests/api/test_apis.py

test-integration:
	@echo "Running integration tests..."
	./scripts/run_tests.sh tests/integration/test_smart_notifications.py

test-docker:
	@echo "Running tests in Docker..."
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

run:
	@echo "Starting development server..."
	python manage.py runserver 0.0.0.0:8007

migrate:
	@echo "Running migrations..."
	python manage.py migrate

makemigrations:
	@echo "Creating migrations..."
	python manage.py makemigrations

setup:
	@echo "Setting up project..."
	pip install -r requirements.txt
	python manage.py migrate
	@echo "Setup complete! Run 'make fixtures' to load sample data."

fixtures:
	@echo "Loading sample data..."
	python scripts/create_sample_data.py

shell:
	python manage.py shell

dbshell:
	python manage.py dbshell

collectstatic:
	python manage.py collectstatic --noinput

celery:
	celery -A celery_app worker --loglevel=info

celery-beat:
	celery -A celery_app beat --loglevel=info

flower:
	flower -A celery_app --port=5555