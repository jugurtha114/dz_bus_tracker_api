#!/bin/bash

# DZ Bus Tracker Entrypoint Script
# This script handles application startup and initialization

set -e

# Function to wait for database
wait_for_db() {
    echo "Waiting for database to be ready..."

    while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
        echo "Database is unavailable - sleeping"
        sleep 1
    done

    echo "Database is ready!"
}

# Function to wait for Redis (uses Python since redis-cli is not in the image)
wait_for_redis() {
    echo "Waiting for Redis to be ready..."

    while ! python -c "
import redis, sys
try:
    r = redis.Redis(host='redis', port=6379, socket_connect_timeout=2)
    r.ping()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        echo "Redis is unavailable - sleeping"
        sleep 1
    done

    echo "Redis is ready!"
}

# Function to run database migrations
run_migrations() {
    echo "Running database migrations..."
    python manage.py makemigrations --noinput
    python manage.py migrate --noinput
    echo "Migrations completed!"
}

# Function to collect static files
collect_static() {
    if [ "$DEBUG" = "0" ] || [ "$DEBUG" = "False" ]; then
        echo "Collecting static files..."
        python manage.py collectstatic --noinput --clear
        echo "Static files collected!"
    else
        echo "Skipping static file collection in development mode"
    fi
}

# Function to load sample data for development
load_sample_data() {
    if [ "$DEBUG" = "1" ] || [ "$DEBUG" = "True" ]; then
        echo "Loading sample data for development..."
        python manage.py shell << EOF
# Add sample data creation logic here if needed
print("Sample data loading completed")
EOF
    fi
}

# Function to start appropriate service
start_service() {
    case "$1" in
        "web")
            echo "Starting ASGI web server..."
            if [ "$DEBUG" = "1" ] || [ "$DEBUG" = "True" ]; then
                uvicorn config.asgi:application --host 0.0.0.0 --port 8007 --reload
            else
                gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8007 --workers 3 --timeout 120
            fi
            ;;
        "celery")
            echo "Starting Celery worker..."
            celery -A config.celery worker --loglevel=info --concurrency=4
            ;;
        "celery-beat")
            echo "Starting Celery beat scheduler..."
            celery -A config.celery beat --loglevel=info
            ;;
        "flower")
            echo "Starting Flower monitoring..."
            celery -A config.celery flower --port=5555
            ;;
        *)
            echo "Starting ASGI web server (default)..."
            if [ "$DEBUG" = "1" ] || [ "$DEBUG" = "True" ]; then
                uvicorn config.asgi:application --host 0.0.0.0 --port 8007 --reload
            else
                gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8007 --workers 3 --timeout 120
            fi
            ;;
    esac
}

# Main execution
echo "Starting DZ Bus Tracker application..."

# Wait for dependencies
wait_for_db
wait_for_redis

# Run initialization tasks
run_migrations
collect_static

# Load sample data (only for web service)
if [ "${1:-web}" = "web" ]; then
    load_sample_data
fi

# Start the requested service
start_service "${1:-web}"
