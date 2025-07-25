#!/bin/bash

# Health check script for DZ Bus Tracker
# Returns 0 if healthy, 1 if unhealthy

set -e

# Default values
SERVICE_TYPE=${SERVICE_TYPE:-web}
HOST=${HOST:-localhost}
PORT=${PORT:-8000}

# Function to check web service health
check_web_health() {
    echo "Checking web service health..."
    
    # Check if the health endpoint responds
    if curl -f -s "http://${HOST}:${PORT}/health/" > /dev/null 2>&1; then
        echo "Web service is healthy"
        return 0
    else
        echo "Web service is unhealthy"
        return 1
    fi
}

# Function to check Celery worker health
check_celery_health() {
    echo "Checking Celery worker health..."
    
    # Check if Celery worker responds to ping
    if celery -A celery_app inspect ping > /dev/null 2>&1; then
        echo "Celery worker is healthy"
        return 0
    else
        echo "Celery worker is unhealthy"
        return 1
    fi
}

# Function to check database connectivity
check_database_health() {
    echo "Checking database connectivity..."
    
    # Use Django's database check
    if python manage.py check --database default > /dev/null 2>&1; then
        echo "Database connection is healthy"
        return 0
    else
        echo "Database connection is unhealthy"
        return 1
    fi
}

# Function to check Redis connectivity
check_redis_health() {
    echo "Checking Redis connectivity..."
    
    # Check Redis connection
    if redis-cli -h redis -p 6379 ping > /dev/null 2>&1; then
        echo "Redis connection is healthy"
        return 0
    else
        echo "Redis connection is unhealthy"
        return 1
    fi
}

# Main health check based on service type
case "$SERVICE_TYPE" in
    "web")
        check_web_health
        ;;
    "celery")
        check_celery_health
        ;;
    "database")
        check_database_health
        ;;
    "redis")
        check_redis_health
        ;;
    "full")
        # Check all services
        check_web_health && check_celery_health && check_database_health && check_redis_health
        ;;
    *)
        echo "Unknown service type: $SERVICE_TYPE"
        echo "Available types: web, celery, database, redis, full"
        exit 1
        ;;
esac