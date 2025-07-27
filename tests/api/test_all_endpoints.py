#!/usr/bin/env python3
"""
Comprehensive test for all API endpoints to ensure they're working correctly.
"""

import os
import sys
import django
import json
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import Trip

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

class EndpointTester:
    def __init__(self):
        self.client = APIClient()
        self.user = None
        self.driver_user = None
        self.admin_user = None
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'errors': []
        }
        
    def setup_test_users(self):
        """Setup test users with different roles."""
        header("Setting Up Test Users")
        
        # Admin user
        self.admin_user = User.objects.filter(is_superuser=True).first()
        if not self.admin_user:
            self.admin_user = User.objects.create_superuser(
                email='admin@dzbus.com',
                password='admin123'
            )
            success(f"Created admin user: {self.admin_user.email}")
        else:
            info(f"Using existing admin: {self.admin_user.email}")
        
        # Passenger user
        self.user = User.objects.filter(user_type='passenger').first()
        if not self.user:
            self.user = User.objects.create_user(
                email='test_passenger@dzbus.com',
                password='testpass123',
                first_name='Test',
                last_name='Passenger',
                user_type='passenger'
            )
            success(f"Created passenger user: {self.user.email}")
        else:
            info(f"Using existing passenger: {self.user.email}")
        
        # Driver user
        self.driver_user = User.objects.filter(user_type='driver').first()
        if not self.driver_user:
            self.driver_user = User.objects.create_user(
                email='test_driver@dzbus.com',
                password='testpass123',
                first_name='Test',
                last_name='Driver',
                user_type='driver'
            )
            # Create driver profile
            Driver.objects.create(
                user=self.driver_user,
                license_number='TEST123',
                phone='+213555123456',
                status='approved'
            )
            success(f"Created driver user: {self.driver_user.email}")
        else:
            info(f"Using existing driver: {self.driver_user.email}")
        
        return True
    
    def test_endpoint(self, method, url, data=None, user=None, expected_status=None, description=None):
        """Test a single endpoint."""
        self.results['total'] += 1
        
        # Set authentication
        if user:
            self.client.force_authenticate(user=user)
        else:
            self.client.force_authenticate(user=None)
        
        # Make request
        try:
            if method == 'GET':
                response = self.client.get(url)
            elif method == 'POST':
                response = self.client.post(url, data, format='json')
            elif method == 'PUT':
                response = self.client.put(url, data, format='json')
            elif method == 'PATCH':
                response = self.client.patch(url, data, format='json')
            elif method == 'DELETE':
                response = self.client.delete(url)
            else:
                error(f"Unknown method: {method}")
                return False
            
            # Check response
            if expected_status:
                if response.status_code == expected_status:
                    success(f"{method} {url} - {response.status_code} (Expected: {expected_status})")
                    self.results['passed'] += 1
                    return True
                else:
                    error(f"{method} {url} - {response.status_code} (Expected: {expected_status})")
                    if response.data:
                        error(f"  Response: {response.data}")
                    self.results['failed'] += 1
                    self.results['errors'].append({
                        'endpoint': f"{method} {url}",
                        'expected': expected_status,
                        'actual': response.status_code,
                        'response': response.data if hasattr(response, 'data') else str(response.content)
                    })
                    return False
            else:
                # Accept any 2xx status
                if 200 <= response.status_code < 300:
                    success(f"{method} {url} - {response.status_code}")
                    self.results['passed'] += 1
                    return True
                else:
                    error(f"{method} {url} - {response.status_code}")
                    if hasattr(response, 'data') and response.data:
                        error(f"  Response: {response.data}")
                    self.results['failed'] += 1
                    self.results['errors'].append({
                        'endpoint': f"{method} {url}",
                        'status': response.status_code,
                        'response': response.data if hasattr(response, 'data') else str(response.content)
                    })
                    return False
                    
        except Exception as e:
            error(f"{method} {url} - Exception: {str(e)}")
            self.results['failed'] += 1
            self.results['errors'].append({
                'endpoint': f"{method} {url}",
                'exception': str(e)
            })
            return False
    
    def test_auth_endpoints(self):
        """Test authentication endpoints."""
        header("Testing Authentication Endpoints")
        
        # Test registration
        register_data = {
            'email': f'newuser_{datetime.now().timestamp()}@dzbus.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'New',
            'last_name': 'User',
            'user_type': 'passenger'
        }
        self.test_endpoint('POST', '/api/v1/accounts/register/', register_data, expected_status=201)
        
        # Test login
        login_data = {
            'email': self.user.email,
            'password': 'testpass123'
        }
        self.test_endpoint('POST', '/api/v1/accounts/login/', login_data, expected_status=200)
        
        # Test profile (authenticated)
        self.test_endpoint('GET', '/api/v1/accounts/profile/', user=self.user)
        
        # Test logout
        self.test_endpoint('POST', '/api/v1/accounts/logout/', user=self.user)
    
    def test_buses_endpoints(self):
        """Test buses endpoints."""
        header("Testing Buses Endpoints")
        
        # Public endpoints
        self.test_endpoint('GET', '/api/v1/buses/')
        
        # Get first bus for detail test
        bus = Bus.objects.first()
        if bus:
            self.test_endpoint('GET', f'/api/v1/buses/{bus.id}/')
            self.test_endpoint('GET', f'/api/v1/buses/{bus.id}/location/')
            self.test_endpoint('GET', f'/api/v1/buses/{bus.id}/current_trip/')
        
        # Admin endpoints
        bus_data = {
            'bus_number': f'TEST{datetime.now().timestamp():.0f}',
            'capacity': 50,
            'model': 'Test Model',
            'status': 'active'
        }
        self.test_endpoint('POST', '/api/v1/buses/', bus_data, user=self.admin_user)
    
    def test_drivers_endpoints(self):
        """Test drivers endpoints."""
        header("Testing Drivers Endpoints")
        
        # Public endpoints
        self.test_endpoint('GET', '/api/v1/drivers/')
        
        # Get first driver for detail test
        driver = Driver.objects.filter(status='approved').first()
        if driver:
            self.test_endpoint('GET', f'/api/v1/drivers/{driver.id}/')
            self.test_endpoint('GET', f'/api/v1/drivers/{driver.id}/ratings/')
            self.test_endpoint('GET', f'/api/v1/drivers/{driver.id}/trips/')
        
        # Driver registration
        driver_data = {
            'email': f'driver_{datetime.now().timestamp()}@dzbus.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'Test',
            'last_name': 'Driver',
            'user_type': 'driver',
            'license_number': f'LIC{datetime.now().timestamp():.0f}',
            'phone': '+213555000000'
        }
        self.test_endpoint('POST', '/api/v1/drivers/register/', driver_data)
    
    def test_lines_endpoints(self):
        """Test lines endpoints."""
        header("Testing Lines Endpoints")
        
        # Public endpoints
        self.test_endpoint('GET', '/api/v1/lines/')
        
        # Get first line for detail test
        line = Line.objects.first()
        if line:
            self.test_endpoint('GET', f'/api/v1/lines/{line.id}/')
            self.test_endpoint('GET', f'/api/v1/lines/{line.id}/stops/')
            self.test_endpoint('GET', f'/api/v1/lines/{line.id}/schedules/')
            self.test_endpoint('GET', f'/api/v1/lines/{line.id}/buses/')
        
        # Test stops
        self.test_endpoint('GET', '/api/v1/lines/stops/')
        stop = Stop.objects.first()
        if stop:
            self.test_endpoint('GET', f'/api/v1/lines/stops/{stop.id}/')
            self.test_endpoint('GET', f'/api/v1/lines/stops/{stop.id}/lines/')
        
        # Test schedules
        self.test_endpoint('GET', '/api/v1/lines/schedules/')
    
    def test_tracking_endpoints(self):
        """Test tracking endpoints."""
        header("Testing Tracking Endpoints")
        
        # Public endpoints
        self.test_endpoint('GET', '/api/v1/tracking/active-buses/')
        self.test_endpoint('GET', '/api/v1/tracking/bus-lines/')
        self.test_endpoint('GET', '/api/v1/tracking/trips/')
        
        # Get first trip for detail test
        trip = Trip.objects.first()
        if trip:
            self.test_endpoint('GET', f'/api/v1/tracking/trips/{trip.id}/')
        
        # Test waiting passengers
        self.test_endpoint('GET', '/api/v1/tracking/waiting-passengers/')
        
        # Driver endpoints
        if self.driver_user:
            driver = Driver.objects.filter(user=self.driver_user).first()
            if driver:
                bus = Bus.objects.filter(driver=driver).first()
                if not bus:
                    bus = Bus.objects.filter(driver__isnull=True).first()
                    if bus:
                        bus.driver = driver
                        bus.save()
                
                if bus:
                    # Start trip
                    trip_data = {
                        'line_id': str(Line.objects.first().id) if Line.objects.exists() else None
                    }
                    if trip_data['line_id']:
                        self.test_endpoint('POST', '/api/v1/tracking/trips/start_trip/', 
                                         trip_data, user=self.driver_user)
    
    def test_notifications_endpoints(self):
        """Test notifications endpoints."""
        header("Testing Notifications Endpoints")
        
        # User endpoints
        self.test_endpoint('GET', '/api/v1/notifications/notifications/', user=self.user)
        self.test_endpoint('GET', '/api/v1/notifications/notifications/unread_count/', user=self.user)
        self.test_endpoint('POST', '/api/v1/notifications/notifications/mark_all_read/', user=self.user)
        
        # Device tokens
        token_data = {
            'token': f'test_token_{datetime.now().timestamp()}',
            'device_type': 'android'
        }
        self.test_endpoint('POST', '/api/v1/notifications/device-tokens/', 
                         token_data, user=self.user, expected_status=201)
        
        # Preferences
        self.test_endpoint('GET', '/api/v1/notifications/preferences/my_preferences/', user=self.user)
        
        # Schedules
        self.test_endpoint('GET', '/api/v1/notifications/schedules/', user=self.user)
        
        # System notifications (admin)
        self.test_endpoint('GET', '/api/v1/notifications/system/', user=self.admin_user)
    
    def test_gamification_endpoints(self):
        """Test gamification endpoints."""
        header("Testing Gamification Endpoints")
        
        # Profile
        self.test_endpoint('GET', '/api/v1/gamification/profile/me/', user=self.user)
        
        # Achievements
        self.test_endpoint('GET', '/api/v1/gamification/achievements/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/achievements/progress/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/achievements/unlocked/', user=self.user)
        
        # Transactions
        self.test_endpoint('GET', '/api/v1/gamification/transactions/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/transactions/summary/', user=self.user)
        
        # Leaderboards
        for period in ['daily', 'weekly', 'monthly', 'all_time']:
            self.test_endpoint('GET', f'/api/v1/gamification/leaderboard/{period}/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/leaderboard/my_rank/', user=self.user)
        
        # Challenges
        self.test_endpoint('GET', '/api/v1/gamification/challenges/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/challenges/my_challenges/', user=self.user)
        
        # Rewards
        self.test_endpoint('GET', '/api/v1/gamification/rewards/', user=self.user)
        self.test_endpoint('GET', '/api/v1/gamification/rewards/my_rewards/', user=self.user)
    
    def test_offline_endpoints(self):
        """Test offline mode endpoints."""
        header("Testing Offline Mode Endpoints")
        
        # Configuration
        self.test_endpoint('GET', '/api/v1/offline/config/current/', user=self.user)
        
        # Cache management
        self.test_endpoint('GET', '/api/v1/offline/cache/status/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/cache/statistics/', user=self.user)
        self.test_endpoint('POST', '/api/v1/offline/cache/sync/', {'force': False}, user=self.user)
        
        # Cached data
        self.test_endpoint('GET', '/api/v1/offline/data/lines/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/data/stops/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/data/schedules/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/data/buses/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/data/notifications/', user=self.user)
        
        # Sync queue
        self.test_endpoint('GET', '/api/v1/offline/sync-queue/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/sync-queue/pending/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/sync-queue/failed/', user=self.user)
        
        # Logs
        self.test_endpoint('GET', '/api/v1/offline/logs/', user=self.user)
        self.test_endpoint('GET', '/api/v1/offline/logs/summary/', user=self.user)
    
    def test_schema_endpoints(self):
        """Test API schema endpoints."""
        header("Testing API Schema Endpoints")
        
        # OpenAPI schema
        self.test_endpoint('GET', '/api/schema/')
        self.test_endpoint('GET', '/api/schema/swagger-ui/')
        self.test_endpoint('GET', '/api/schema/redoc/')
    
    def run_all_tests(self):
        """Run all endpoint tests."""
        print(f"\n{BLUE}DZ Bus Tracker - API Endpoint Test{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        if not self.setup_test_users():
            error("Failed to setup test users")
            return
        
        # Run all test categories
        self.test_auth_endpoints()
        self.test_buses_endpoints()
        self.test_drivers_endpoints()
        self.test_lines_endpoints()
        self.test_tracking_endpoints()
        self.test_notifications_endpoints()
        self.test_gamification_endpoints()
        self.test_offline_endpoints()
        self.test_schema_endpoints()
        
        # Summary
        header("Test Summary")
        print(f"Total endpoints tested: {self.results['total']}")
        print(f"Passed: {self.results['passed']} ({self.results['passed']/self.results['total']*100:.1f}%)")
        print(f"Failed: {self.results['failed']} ({self.results['failed']/self.results['total']*100:.1f}%)")
        
        if self.results['failed'] > 0:
            print(f"\n{RED}Failed Endpoints:{RESET}")
            for error_detail in self.results['errors'][:10]:  # Show first 10 errors
                print(f"\n{RED}• {error_detail['endpoint']}{RESET}")
                if 'expected' in error_detail:
                    print(f"  Expected: {error_detail['expected']}, Got: {error_detail['actual']}")
                elif 'status' in error_detail:
                    print(f"  Status: {error_detail['status']}")
                elif 'exception' in error_detail:
                    print(f"  Exception: {error_detail['exception']}")
                if 'response' in error_detail and error_detail['response']:
                    print(f"  Response: {error_detail['response']}")
            
            if len(self.results['errors']) > 10:
                print(f"\n... and {len(self.results['errors']) - 10} more errors")
        
        # Success message
        if self.results['failed'] == 0:
            print(f"\n{GREEN}All endpoints are working correctly!{RESET}")
        else:
            print(f"\n{YELLOW}Some endpoints need attention. Please check the errors above.{RESET}")

if __name__ == '__main__':
    tester = EndpointTester()
    tester.run_all_tests()