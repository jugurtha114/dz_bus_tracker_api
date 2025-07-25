#!/bin/bash
# Load fixtures for DZ Bus Tracker

echo "Loading DZ Bus Tracker fixtures..."

# Load in order of dependencies
echo "Loading users..."
python manage.py loaddata fixtures/01_users.json

echo "Loading groups..."
python manage.py loaddata fixtures/02_groups.json

echo "Loading drivers..."
python manage.py loaddata fixtures/03_drivers.json

echo "Loading buses..."
python manage.py loaddata fixtures/04_buses.json

echo "Loading lines and stops..."
python manage.py loaddata fixtures/05_lines.json

echo "Loading tracking data..."
python manage.py loaddata fixtures/06_tracking.json

echo "Loading notifications..."
python manage.py loaddata fixtures/07_notifications.json

echo "✓ All fixtures loaded successfully!"
