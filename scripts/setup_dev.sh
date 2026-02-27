#!/bin/bash
# Setup script for local development (outside Docker).
# Runs migrations and creates dev users.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Running migrations..."
python manage.py migrate --noinput

echo ""
echo "Creating development users..."
python manage.py create_dev_users

echo ""
echo "Local dev setup complete."
