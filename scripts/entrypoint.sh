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

# Function to wait for Redis
wait_for_redis() {
    echo "Waiting for Redis to be ready..."
    
    while ! redis-cli -h redis -p 6379 ping > /dev/null 2>&1; do
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

# Function to create superuser if it doesn't exist
create_superuser() {
    echo "Creating superuser if it doesn't exist..."
    python manage.py shell << EOF
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()

try:
    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser(
            email='admin@dzbustracker.com',
            password='admin123',
            first_name='Admin',
            last_name='User'
        )
        print("Superuser created: admin@dzbustracker.com / admin123")
    else:
        print("Superuser already exists")
except IntegrityError:
    print("Superuser creation failed - user may already exist")
EOF
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
            echo "Starting Django web server..."
            if [ "$DEBUG" = "1" ] || [ "$DEBUG" = "True" ]; then
                python manage.py runserver 0.0.0.0:8000
            else
                gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 config.wsgi:application
            fi
            ;;
        "celery")
            echo "Starting Celery worker..."
            celery -A celery_app worker --loglevel=info --concurrency=4
            ;;
        "celery-beat")
            echo "Starting Celery beat scheduler..."
            celery -A celery_app beat --loglevel=info
            ;;
        "flower")
            echo "Starting Flower monitoring..."
            celery -A celery_app flower --port=5555
            ;;
        *)
            echo "Starting Django web server (default)..."
            if [ "$DEBUG" = "1" ] || [ "$DEBUG" = "True" ]; then
                python manage.py runserver 0.0.0.0:8000
            else
                gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 config.wsgi:application
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

# Create superuser (only for web service)
if [ "${1:-web}" = "web" ]; then
    create_superuser
    load_sample_data
fi

# Start the requested service
start_service "${1:-web}"