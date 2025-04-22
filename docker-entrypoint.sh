#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

postgres_ready() {
python << END
import sys
import psycopg
import environ
import os

env = environ.Env()
try:
    if os.path.exists("/.env"):
        env.read_env("/.env")
    elif os.path.exists(".env"):
        env.read_env(".env")
    
    dbname = env.str("POSTGRES_DB", "postgres")
    user = env.str("POSTGRES_USER", "postgres")
    password = env.str("POSTGRES_PASSWORD", "postgres")
    host = env.str("DATABASE_HOST", "db")
    port = env.str("DATABASE_PORT", "5432")
    
    conn = psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
    )
except psycopg2.OperationalError:
    sys.exit(-1)
sys.exit(0)
END
}

redis_ready() {
python << END
import sys
import os
import environ
import redis

env = environ.Env()
try:
    if os.path.exists("/.env"):
        env.read_env("/.env")
    elif os.path.exists(".env"):
        env.read_env(".env")
    
    redis_host = env.str("REDIS_HOST", "redis")
    redis_port = env.int("REDIS_PORT", 6379)
    redis_password = env.str("REDIS_PASSWORD", "")
    
    rs = redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        db=0,
        socket_timeout=5,
    )
    rs.ping()
except redis.exceptions.RedisError:
    sys.exit(-1)
sys.exit(0)
END
}

until postgres_ready; do
  >&2 echo 'Waiting for PostgreSQL to become available...'
  sleep 1
done
>&2 echo 'PostgreSQL is available'

until redis_ready; do
  >&2 echo 'Waiting for Redis to become available...'
  sleep 1
done
>&2 echo 'Redis is available'

# Apply database migrations
>&2 echo 'Applying database migrations...'
python manage.py migrate

# Collect static files
>&2 echo 'Collecting static files...'
python manage.py collectstatic --noinput

# Create superuser if needed (for development)
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.local" ]; then
  python manage.py createsuperuser --noinput || true
fi

exec "$@"
