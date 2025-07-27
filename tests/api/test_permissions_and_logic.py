#!/usr/bin/env python3
"""
Comprehensive permission and logic tests for DZ Bus Tracker.
Tests all user types and their access to different endpoints.
"""

import os
import sys
import django
import json
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import LocationUpdate, Trip
from apps.core.constants import *

User = get_user_model()

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

def header(msg):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{msg.center(60)}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

class PermissionTester:
    def __init__(self):
        self.client = APIClient()
        self.users = {}
        self.tokens = {}
        self.test_results = []
        
    def setup_test_users(self):
        """Setup test users for permission testing."""
        header("Setting Up Test Users")
        
        # Create users
        self.users['admin'] = User.objects.filter(email='admin@dzbus.com').first()
        self.users['manager'] = User.objects.filter(email='manager@dzbus.com').first()
        self.users['driver'] = User.objects.filter(email='ahmed.driver@dzbus.com').first()
        self.users['driver_pending'] = User.objects.filter(email='karim.driver@dzbus.com').first()
        self.users['passenger'] = User.objects.filter(email='fatima@dzbus.com').first()
        
        # Get tokens
        for role, user in self.users.items():
            if user:
                self.client.force_authenticate(user=user)
                response = self.client.post('/api/token/', {
                    'email': user.email,
                    'password': 'admin123' if 'admin' in role or 'manager' in role else ('driver123' if 'driver' in role else 'pass123')
                })
                if response.status_code == 200:
                    self.tokens[role] = response.data['access']
                    success(f"Setup {role}: {user.email}")
                else:
                    error(f"Failed to get token for {role}")
        
        self.client.force_authenticate(user=None)
    
    def test_endpoint(self, user_type, method, endpoint, data=None, expected_status=None, description=""):
        """Test a single endpoint with a specific user type."""
        user = self.users.get(user_type)
        if not user:
            error(f"User type {user_type} not found")
            return None
            
        self.client.force_authenticate(user=user)
        
        if method == 'GET':
            response = self.client.get(endpoint)
        elif method == 'POST':
            response = self.client.post(endpoint, data, format='json')
        elif method == 'PUT':
            response = self.client.put(endpoint, data, format='json')
        elif method == 'PATCH':
            response = self.client.patch(endpoint, data, format='json')
        elif method == 'DELETE':
            response = self.client.delete(endpoint)
        else:
            error(f"Unknown method: {method}")
            return None
        
        # Check if response matches expected status
        if expected_status:
            if response.status_code == expected_status:
                success(f"{user_type.upper()} - {method} {endpoint}: {response.status_code} (Expected)")
            else:
                error(f"{user_type.upper()} - {method} {endpoint}: {response.status_code} (Expected: {expected_status})")
        else:
            info(f"{user_type.upper()} - {method} {endpoint}: {response.status_code}")
        
        self.test_results.append({
            'user_type': user_type,
            'method': method,
            'endpoint': endpoint,
            'status': response.status_code,
            'expected': expected_status,
            'passed': response.status_code == expected_status if expected_status else True,
            'description': description
        })
        
        return response
    
    def test_user_endpoints(self):
        """Test user-related endpoints with different permissions."""
        header("Testing User Endpoints")
        
        # Test /users/me endpoint
        info("Testing /api/v1/accounts/users/me/")
        self.test_endpoint('admin', 'GET', '/api/v1/accounts/users/me/', expected_status=200)
        self.test_endpoint('driver', 'GET', '/api/v1/accounts/users/me/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/accounts/users/me/', expected_status=200)
        
        # Test user list (admin only)
        info("\nTesting /api/v1/accounts/users/")
        self.test_endpoint('admin', 'GET', '/api/v1/accounts/users/', expected_status=200)
        self.test_endpoint('manager', 'GET', '/api/v1/accounts/users/', expected_status=200)
        self.test_endpoint('driver', 'GET', '/api/v1/accounts/users/', expected_status=200, 
                          description="Should only see themselves")
        self.test_endpoint('passenger', 'GET', '/api/v1/accounts/users/', expected_status=200,
                          description="Should only see themselves")
        
        # Test profile endpoints
        info("\nTesting /api/v1/accounts/profiles/me/")
        self.test_endpoint('admin', 'GET', '/api/v1/accounts/profiles/me/', expected_status=200)
        self.test_endpoint('driver', 'GET', '/api/v1/accounts/profiles/me/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/accounts/profiles/me/', expected_status=200)
    
    def test_driver_endpoints(self):
        """Test driver-specific endpoints."""
        header("Testing Driver Endpoints")
        
        # Test driver list
        info("Testing /api/v1/drivers/")
        self.test_endpoint('admin', 'GET', '/api/v1/drivers/', expected_status=200)
        self.test_endpoint('manager', 'GET', '/api/v1/drivers/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/drivers/', expected_status=200)
        
        # Test driver profile (drivers only)
        info("\nTesting /api/v1/drivers/drivers/profile/")
        self.test_endpoint('driver', 'GET', '/api/v1/drivers/drivers/profile/', expected_status=200)
        self.test_endpoint('driver_pending', 'GET', '/api/v1/drivers/drivers/profile/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/drivers/drivers/profile/', expected_status=404,
                          description="Passengers don't have driver profiles")
        
        # Test driver approval (admin only)
        driver = Driver.objects.filter(status=DRIVER_STATUS_PENDING).first()
        if driver:
            info(f"\nTesting driver approval for {driver.user.get_full_name()}")
            self.test_endpoint('admin', 'PATCH', f'/api/v1/drivers/drivers/{driver.id}/', 
                             {'status': DRIVER_STATUS_APPROVED}, expected_status=200)
            self.test_endpoint('manager', 'PATCH', f'/api/v1/drivers/drivers/{driver.id}/', 
                             {'status': DRIVER_STATUS_APPROVED}, expected_status=403)
            self.test_endpoint('passenger', 'PATCH', f'/api/v1/drivers/drivers/{driver.id}/', 
                             {'status': DRIVER_STATUS_APPROVED}, expected_status=403)
    
    def test_bus_endpoints(self):
        """Test bus-related endpoints."""
        header("Testing Bus Endpoints")
        
        # Test bus list (all can view)
        info("Testing /api/v1/buses/buses/")
        self.test_endpoint('admin', 'GET', '/api/v1/buses/buses/', expected_status=200)
        self.test_endpoint('driver', 'GET', '/api/v1/buses/buses/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/buses/buses/', expected_status=200)
        
        # Test bus creation (admin only)
        driver = Driver.objects.filter(status=DRIVER_STATUS_APPROVED).first()
        if driver:
            bus_data = {
                'license_plate': '12345-678-09',  # Valid Algerian format
                'driver': driver.id,
                'model': 'Test Model',
                'manufacturer': 'Test Manufacturer',
                'year': 2024,
                'capacity': 30,
                'status': BUS_STATUS_ACTIVE
            }
            info("\nTesting bus creation")
            self.test_endpoint('admin', 'POST', '/api/v1/buses/buses/', bus_data, expected_status=201)
            self.test_endpoint('driver', 'POST', '/api/v1/buses/buses/', bus_data, expected_status=403)
            self.test_endpoint('passenger', 'POST', '/api/v1/buses/buses/', bus_data, expected_status=403)
    
    def test_tracking_endpoints(self):
        """Test tracking-related endpoints."""
        header("Testing Tracking Endpoints")
        
        # Test location updates (all can view)
        info("Testing /api/v1/tracking/locations/")
        self.test_endpoint('admin', 'GET', '/api/v1/tracking/locations/', expected_status=200)
        self.test_endpoint('driver', 'GET', '/api/v1/tracking/locations/', expected_status=200)
        self.test_endpoint('passenger', 'GET', '/api/v1/tracking/locations/', expected_status=200)
        
        # Test location update creation (drivers only)
        bus = Bus.objects.filter(status=BUS_STATUS_ACTIVE).first()
        if bus:
            location_data = {
                'bus': bus.id,
                'latitude': 36.7538,
                'longitude': 3.0588,
                'speed': 35.5,
                'heading': 180
            }
            info("\nTesting location update creation")
            
            # Driver of the bus should be able to update
            if bus.driver:
                self.test_endpoint('driver', 'POST', '/api/v1/tracking/locations/', 
                                 location_data, expected_status=201,
                                 description="Driver can update their bus location")
            
            self.test_endpoint('passenger', 'POST', '/api/v1/tracking/locations/', 
                             location_data, expected_status=403)
        
        # Test waiting passengers report
        stop = Stop.objects.first()
        line = Line.objects.first()
        if stop and line:
            waiting_data = {
                'stop': stop.id,
                'line': line.id,
                'count': 5
            }
            info("\nTesting waiting passengers report")
            self.test_endpoint('passenger', 'POST', '/api/v1/tracking/waiting-passengers/', 
                             waiting_data, expected_status=201,
                             description="Passengers can report waiting")
            self.test_endpoint('driver', 'POST', '/api/v1/tracking/waiting-passengers/', 
                             waiting_data, expected_status=201,
                             description="Drivers can also report")
    
    def test_business_logic(self):
        """Test business logic and constraints."""
        header("Testing Business Logic")
        
        # Test driver can only be assigned to one active bus
        info("Testing bus assignment logic")
        driver = Driver.objects.filter(status=DRIVER_STATUS_APPROVED).first()
        if driver:
            # Check if driver already has an active bus
            active_buses = Bus.objects.filter(driver=driver, status=BUS_STATUS_ACTIVE).count()
            info(f"Driver {driver.user.get_full_name()} has {active_buses} active buses")
            
            if active_buses > 1:
                error("LOGIC ERROR: Driver assigned to multiple active buses!")
            else:
                success("Driver assignment logic correct")
        
        # Test trip constraints
        info("\nTesting trip logic")
        active_trips = Trip.objects.filter(end_time__isnull=True)
        for trip in active_trips:
            # Check if bus has multiple active trips
            bus_trips = active_trips.filter(bus=trip.bus).count()
            if bus_trips > 1:
                error(f"LOGIC ERROR: Bus {trip.bus.license_plate} has {bus_trips} active trips!")
        
        if not active_trips:
            info("No active trips to test")
        else:
            success("Trip logic verified")
        
        # Test passenger count constraints
        info("\nTesting passenger count logic")
        from apps.tracking.models import PassengerCount
        counts = PassengerCount.objects.all()
        for count in counts[:5]:  # Check first 5
            if count.count > count.bus.capacity:
                error(f"LOGIC ERROR: Bus {count.bus.license_plate} has {count.count} passengers but capacity is {count.bus.capacity}")
            else:
                success(f"Bus {count.bus.license_plate}: {count.count}/{count.bus.capacity} passengers")
    
    def test_data_isolation(self):
        """Test that users can only see appropriate data."""
        header("Testing Data Isolation")
        
        # Test that regular users can only see their own data
        info("Testing user data isolation")
        
        # As passenger, should only see own profile
        self.client.force_authenticate(user=self.users['passenger'])
        response = self.client.get('/api/v1/accounts/users/')
        if response.status_code == 200:
            users = response.data.get('results', response.data if isinstance(response.data, list) else [])
            if len(users) == 1 and users[0]['email'] == self.users['passenger'].email:
                success("Passenger can only see their own user data")
            else:
                error(f"Passenger can see {len(users)} users - should only see themselves")
        
        # As admin, should see all users
        self.client.force_authenticate(user=self.users['admin'])
        response = self.client.get('/api/v1/accounts/users/')
        if response.status_code == 200:
            users = response.data.get('results', response.data if isinstance(response.data, list) else [])
            if len(users) > 1:
                success(f"Admin can see all {len(users)} users")
            else:
                error("Admin should see all users")
    
    def print_summary(self):
        """Print test summary."""
        header("Test Summary")
        
        passed = sum(1 for r in self.test_results if r['passed'])
        failed = sum(1 for r in self.test_results if not r['passed'])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"{GREEN}Passed: {passed}{RESET}")
        print(f"{RED}Failed: {failed}{RESET}")
        
        if failed > 0:
            print(f"\n{RED}Failed Tests:{RESET}")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  - {result['user_type']} {result['method']} {result['endpoint']}: "
                          f"Got {result['status']}, Expected {result['expected']}")
    
    def run_all_tests(self):
        """Run all permission and logic tests."""
        print(f"\n{BLUE}DZ Bus Tracker - Permission & Logic Tests{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        self.setup_test_users()
        
        # Run all test suites
        self.test_user_endpoints()
        self.test_driver_endpoints()
        self.test_bus_endpoints()
        self.test_tracking_endpoints()
        self.test_business_logic()
        self.test_data_isolation()
        
        self.print_summary()

if __name__ == '__main__':
    # Make sure we have data
    from apps.accounts.models import User
    if not User.objects.filter(email='admin@dzbus.com').exists():
        print(f"{RED}No test data found. Please run: python create_sample_data.py{RESET}")
        sys.exit(1)
    
    tester = PermissionTester()
    tester.run_all_tests()