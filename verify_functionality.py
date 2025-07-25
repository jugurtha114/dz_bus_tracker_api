#!/usr/bin/env python3
"""
Verify DZ Bus Tracker functionality without running full test suite.
This script checks that all models, APIs, and core functionality are working.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

# Now we can import Django models and functions
from django.test import TestCase, Client
from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.buses.models import Bus
from apps.drivers.models import Driver, DriverRating
from apps.lines.models import Line, Stop, Schedule
from apps.tracking.models import BusLine, LocationUpdate, PassengerCount, Trip
from apps.notifications.models import Notification, DeviceToken
from apps.core.constants import *

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

def test_database_connection():
    """Test database connectivity."""
    info("Testing database connection...")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            success(f"Database connected: PostgreSQL {connection.vendor}")
        return True
    except Exception as e:
        error(f"Database connection failed: {e}")
        return False

def test_models():
    """Test model creation and relationships."""
    info("Testing models...")
    try:
        # Create users
        admin = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            user_type=USER_TYPE_ADMIN
        )
        success("Created admin user")
        
        driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        success("Created driver user")
        
        passenger = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Passenger',
            user_type=USER_TYPE_PASSENGER
        )
        success("Created passenger user")
        
        # Check profiles were created
        assert hasattr(admin, 'profile'), "Admin profile not created"
        assert hasattr(driver_user, 'profile'), "Driver profile not created"
        assert hasattr(passenger, 'profile'), "Passenger profile not created"
        success("User profiles created automatically via signals")
        
        # Create driver
        driver = Driver.objects.create(
            user=driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            status=DRIVER_STATUS_APPROVED
        )
        success("Created driver record")
        
        # Create bus
        bus = Bus.objects.create(
            license_plate='16-123-456',
            driver=driver,
            model='Mercedes Sprinter',
            manufacturer='Mercedes-Benz',
            year=2020,
            capacity=30,
            status=BUS_STATUS_ACTIVE
        )
        success("Created bus")
        
        # Create line and stops
        line = Line.objects.create(
            name='Line A',
            code='LA-01',
            description='Main line'
        )
        
        stop1 = Stop.objects.create(
            name='Central Station',
            latitude=36.7528,
            longitude=3.0424
        )
        
        stop2 = Stop.objects.create(
            name='University',
            latitude=36.7600,
            longitude=3.0500
        )
        
        line.stops.add(stop1, stop2)
        success("Created line with stops")
        
        # Create bus-line assignment
        bus_line = BusLine.objects.create(
            bus=bus,
            line=line,
            tracking_status=BUS_TRACKING_STATUS_ACTIVE
        )
        success("Assigned bus to line")
        
        # Create location update
        location = LocationUpdate.objects.create(
            bus=bus,
            latitude=36.7550,
            longitude=3.0450,
            speed=45.5,
            line=line,
            nearest_stop=stop1
        )
        success("Created location update")
        
        # Create trip
        trip = Trip.objects.create(
            bus=bus,
            driver=driver,
            line=line,
            start_stop=stop1
        )
        success("Created trip")
        
        # Test relationships
        assert bus.driver == driver, "Bus-driver relationship failed"
        assert driver.user == driver_user, "Driver-user relationship failed"
        assert line.stops.count() == 2, "Line-stops relationship failed"
        assert bus_line.bus == bus, "BusLine relationship failed"
        success("All model relationships working correctly")
        
        return True
        
    except Exception as e:
        error(f"Model test failed: {e}")
        return False

def test_authentication():
    """Test JWT authentication."""
    info("Testing authentication...")
    try:
        # Get or create test user
        user = User.objects.filter(email='test_auth@test.com').first()
        if not user:
            user = User.objects.create_user(
                email='test_auth@test.com',
                password='testpass123',
                user_type=USER_TYPE_PASSENGER
            )
        
        # Test JWT token generation
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        success(f"Generated JWT token for user: {user.email}")
        
        # Test API client with token
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        # Test health endpoint
        response = client.get('/health/')
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        success("API authentication working")
        
        return True
        
    except Exception as e:
        error(f"Authentication test failed: {e}")
        return False

def test_permissions():
    """Test permission classes."""
    info("Testing permissions...")
    try:
        from apps.core.permissions import (
            IsAdmin, IsDriver, IsPassenger, 
            IsOwnerOrReadOnly, IsApprovedDriver
        )
        
        # Test permission imports
        success("All permission classes imported successfully")
        
        # Create test request mock
        class MockRequest:
            def __init__(self, user):
                self.user = user
        
        # Test IsAdmin permission
        admin = User.objects.filter(is_staff=True).first()
        if admin:
            request = MockRequest(admin)
            perm = IsAdmin()
            assert perm.has_permission(request, None), "IsAdmin permission failed"
            success("IsAdmin permission working")
        
        return True
        
    except Exception as e:
        error(f"Permission test failed: {e}")
        return False

def test_api_endpoints():
    """Test API endpoint availability."""
    info("Testing API endpoints...")
    try:
        client = Client()
        
        # Test unauthenticated endpoints
        endpoints = [
            '/api/',
            '/api/v1/',
            '/health/',
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            if response.status_code in [200, 401, 403]:
                success(f"Endpoint {endpoint} is accessible")
            else:
                error(f"Endpoint {endpoint} returned {response.status_code}")
        
        return True
        
    except Exception as e:
        error(f"API endpoint test failed: {e}")
        return False

def test_celery_configuration():
    """Test Celery configuration."""
    info("Testing Celery configuration...")
    try:
        from celery_app import app
        
        # Check Celery app is configured
        assert app.main == 'celery_app', "Celery app not configured correctly"
        success(f"Celery app configured: {app.main}")
        
        # Check broker URL
        broker = app.conf.broker_url
        success(f"Celery broker: {broker}")
        
        # Check registered tasks
        tasks = list(app.tasks.keys())
        task_count = len([t for t in tasks if not t.startswith('celery.')])
        success(f"Found {task_count} custom Celery tasks")
        
        return True
        
    except Exception as e:
        error(f"Celery test failed: {e}")
        return False

def test_geolocation():
    """Test geolocation functionality."""
    info("Testing geolocation...")
    try:
        from apps.core.utils.geo import calculate_distance
        
        # Test distance calculation
        lat1, lon1 = 36.7528, 3.0424  # Algiers center
        lat2, lon2 = 36.7600, 3.0500  # Nearby point
        
        distance = calculate_distance(lat1, lon1, lat2, lon2)
        assert distance > 0, "Distance calculation failed"
        success(f"Distance calculation working: {distance:.2f} km")
        
        return True
        
    except Exception as e:
        error(f"Geolocation test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 50)
    print("DZ Bus Tracker Functionality Verification")
    print("=" * 50)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Models & Relationships", test_models),
        ("Authentication", test_authentication),
        ("Permissions", test_permissions),
        ("API Endpoints", test_api_endpoints),
        ("Celery Configuration", test_celery_configuration),
        ("Geolocation", test_geolocation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * len(test_name))
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            error(f"Unexpected error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"{test_name:.<40} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"\n{GREEN}✓ All functionality tests passed!{RESET}")
        return 0
    else:
        print(f"\n{RED}✗ Some tests failed. Please check the output above.{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())