#!/bin/bash
# Quick load essential fixtures only

echo "Loading essential DZ Bus Tracker data..."
python manage.py loaddata fixtures/all_essential_data.json
echo "✓ Essential data loaded successfully!"
