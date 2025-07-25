#!/bin/bash
# Quick test script for DZ Bus Tracker

echo "🚌 DZ Bus Tracker - Quick Test Setup"
echo "===================================="
echo ""

# Check if Django server is running
if ! curl -s http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "⚠️  Django server not running. Starting it now..."
    python manage.py runserver &
    DJANGO_PID=$!
    sleep 3
    echo "✅ Django server started (PID: $DJANGO_PID)"
else
    echo "✅ Django server already running"
fi

echo ""
echo "📊 Loading sample data..."
if [ "$1" == "--fresh" ]; then
    echo "Creating fresh sample data..."
    python create_sample_data.py
else
    echo "Loading fixtures..."
    ./load_essential_fixtures.sh
fi

echo ""
echo "🌐 Starting test interface..."
echo ""
echo "============================================"
echo "🎯 Test Credentials:"
echo "============================================"
echo "Admin:     admin@dzbus.com / admin123"
echo "Manager:   manager@dzbus.com / manager123" 
echo "Driver:    ahmed.driver@dzbus.com / driver123"
echo "Passenger: fatima@dzbus.com / pass123"
echo "============================================"
echo ""
echo "📍 Access Points:"
echo "- Test Interface: http://localhost:8080"
echo "- API Docs: http://localhost:8000/api/schema/swagger-ui/"
echo "- Admin Panel: http://localhost:8000/admin/"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Start test interface server
python serve_test_interface.py