#!/bin/bash
# =============================================================================
# DZ Bus Tracker — Production Entrypoint
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Wait for dependencies
# ---------------------------------------------------------------------------
wait_for_db() {
    echo "[entrypoint] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
    local retries=30
    while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "[entrypoint] ERROR: PostgreSQL not ready after 30 attempts"
            exit 1
        fi
        sleep 1
    done
    echo "[entrypoint] PostgreSQL is ready."
}

wait_for_redis() {
    echo "[entrypoint] Waiting for Redis..."
    local retries=20
    while ! python -c "
import redis, sys, os
try:
    url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    r = redis.Redis.from_url(url, socket_connect_timeout=2)
    r.ping()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "[entrypoint] ERROR: Redis not ready after 20 attempts"
            exit 1
        fi
        sleep 1
    done
    echo "[entrypoint] Redis is ready."
}

# ---------------------------------------------------------------------------
# Service start functions
# ---------------------------------------------------------------------------
start_web() {
    echo "[entrypoint] Running migrations..."
    python manage.py migrate --noinput

    echo "[entrypoint] Collecting static files..."
    python manage.py collectstatic --noinput

    local WORKERS=${GUNICORN_WORKERS:-4}
    local THREADS=${GUNICORN_THREADS:-2}
    local TIMEOUT=${GUNICORN_TIMEOUT:-120}
    local MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-2000}
    local MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-200}
    local GRACEFUL_TIMEOUT=${GUNICORN_GRACEFUL_TIMEOUT:-30}

    echo "[entrypoint] Starting Gunicorn + UvicornWorker (${WORKERS} workers, port 8007)..."
    exec gunicorn config.asgi:application \
        --bind 0.0.0.0:8007 \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers "$WORKERS" \
        --timeout "$TIMEOUT" \
        --graceful-timeout "$GRACEFUL_TIMEOUT" \
        --max-requests "$MAX_REQUESTS" \
        --max-requests-jitter "$MAX_REQUESTS_JITTER" \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        --forwarded-allow-ips "*" \
        --proxy-protocol \
        --proxy-allow-from "*"
}

start_celery() {
    local CONCURRENCY=${CELERY_CONCURRENCY:-4}
    local MAX_TASKS=${CELERY_MAX_TASKS_PER_CHILD:-1000}
    local PREFETCH=${CELERY_PREFETCH_MULTIPLIER:-1}

    echo "[entrypoint] Starting Celery worker (concurrency=${CONCURRENCY})..."
    exec celery -A config.celery worker \
        --loglevel=info \
        --concurrency="$CONCURRENCY" \
        --max-tasks-per-child="$MAX_TASKS" \
        --prefetch-multiplier="$PREFETCH" \
        --without-heartbeat \
        --without-mingle \
        --without-gossip \
        -Ofair
}

start_celery_beat() {
    echo "[entrypoint] Starting Celery Beat scheduler..."
    exec celery -A config.celery beat \
        --loglevel=info \
        --pidfile=/tmp/celerybeat.pid \
        --schedule=/tmp/celerybeat-schedule
}

start_flower() {
    echo "[entrypoint] Starting Flower monitoring..."
    exec celery -A config.celery flower \
        --port=5555 \
        --broker_api="redis://:${REDIS_PASSWORD}@redis:6379/0" \
        --basic_auth="${FLOWER_USER:-admin}:${FLOWER_PASSWORD:-changeme}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "[entrypoint] DZ Bus Tracker — starting ${1:-web}..."

wait_for_db
wait_for_redis

case "${1:-web}" in
    web)          start_web ;;
    celery)       start_celery ;;
    celery-beat)  start_celery_beat ;;
    flower)       start_flower ;;
    *)
        echo "[entrypoint] Unknown service: $1"
        echo "Usage: entrypoint.prod.sh {web|celery|celery-beat|flower}"
        exit 1
        ;;
esac
