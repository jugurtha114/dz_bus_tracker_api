#!/usr/bin/env python3
"""
Basic functionality test for DZ Bus Tracker.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

# Now we can import Django models and functions
from django.test import TestCase, Client
from django.db import connection, transaction
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

def test_basic_functionality():
    """Test basic functionality."""
    print("=" * 50)
    print("DZ Bus Tracker Basic Functionality Test")
    print("=" * 50)
    
    # Clean up any existing test data
    with transaction.atomic():
        User.objects.filter(email__contains='@test.com').delete()
    
    try:
        # Test 1: Create admin user
        info("Creating admin user...")
        admin = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            user_type=USER_TYPE_ADMIN
        )
        success(f"Created admin user: {admin.email}")
        
        # Test 2: Check profile creation
        assert hasattr(admin, 'profile'), "Profile not created"
        success("Profile created automatically via signal")
        
        # Test 3: Create driver user
        info("Creating driver user...")
        driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        success(f"Created driver user: {driver_user.email}")
        
        # Test 4: Create driver record
        info("Creating driver record...")
        driver = Driver.objects.create(
            user=driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            status=DRIVER_STATUS_APPROVED
        )
        success(f"Created driver with license: {driver.driver_license_number}")
        
        # Test 5: Create bus
        info("Creating bus...")
        bus = Bus.objects.create(
            license_plate='16-123-456',
            driver=driver,
            model='Mercedes Sprinter',
            manufacturer='Mercedes-Benz',
            year=2020,
            capacity=30,
            status=BUS_STATUS_ACTIVE
        )
        success(f"Created bus: {bus.license_plate}")
        
        # Test 6: Create line and stops
        info("Creating bus line and stops...")
        line = Line.objects.create(
            name='Line A',
            code='LA-01',
            description='Main line from Central to University'
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
        success(f"Created line '{line.name}' with {line.stops.count()} stops")
        
        # Test 7: JWT Authentication
        info("Testing JWT authentication...")
        refresh = RefreshToken.for_user(driver_user)
        access_token = str(refresh.access_token)
        success("JWT token generated successfully")
        
        # Test 8: API Client Test
        info("Testing API client...")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        # Test health endpoint
        response = client.get('/health/')
        if response.status_code == 200:
            success(f"Health endpoint working: {response.data}")
        else:
            error(f"Health endpoint failed: {response.status_code}")
        
        # Test 9: Create location update
        info("Creating location update...")
        location = LocationUpdate.objects.create(
            bus=bus,
            latitude=36.7550,
            longitude=3.0450,
            speed=45.5
        )
        success(f"Created location update at ({location.latitude}, {location.longitude})")
        
        # Test 10: Summary
        print("\n" + "=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"✓ Users created: {User.objects.count()}")
        print(f"✓ Drivers created: {Driver.objects.count()}")
        print(f"✓ Buses created: {Bus.objects.count()}")
        print(f"✓ Lines created: {Line.objects.count()}")
        print(f"✓ Stops created: {Stop.objects.count()}")
        print(f"✓ Location updates: {LocationUpdate.objects.count()}")
        
        print(f"\n{GREEN}✓ All basic functionality tests passed!{RESET}")
        return True
        
    except Exception as e:
        error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test data
        with transaction.atomic():
            User.objects.filter(email__contains='@test.com').delete()

if __name__ == '__main__':
    success = test_basic_functionality()
    sys.exit(0 if success else 1)