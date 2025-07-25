#!/usr/bin/env python3
"""
Test the Smart Notifications features and API endpoints.
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
from django.contrib.auth import get_user_model
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import Trip, LocationUpdate
from apps.notifications.models import Notification, NotificationPreference, DeviceToken

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

class SmartNotificationTester:
    def __init__(self):
        self.client = APIClient()
        self.user = None
        self.driver = None
        self.bus = None
        self.line = None
        self.stop = None
        
    def setup_test_data(self):
        """Setup test data for notifications."""
        header("Setting Up Test Data")
        
        # Get or create a passenger user
        self.user = User.objects.filter(user_type='passenger').first()
        if not self.user:
            self.user = User.objects.create_user(
                email='test_passenger@example.com',
                password='testpass123',
                first_name='Test',
                last_name='Passenger',
                user_type='passenger'
            )
            success(f"Created test passenger: {self.user.email}")
        else:
            info(f"Using existing passenger: {self.user.email}")
        
        # Get a driver
        self.driver = Driver.objects.filter(status='approved').first()
        if not self.driver:
            error("No approved driver found")
            return False
            
        # Get a bus
        self.bus = Bus.objects.filter(status='active').first()
        if not self.bus:
            error("No active bus found")
            return False
            
        # Get a line and stop
        self.line = Line.objects.filter(is_active=True).first()
        if not self.line:
            error("No active line found")
            return False
            
        self.stop = self.line.stops.first()
        if not self.stop:
            error("No stops found on line")
            return False
            
        info(f"Using bus: {self.bus.bus_number}")
        info(f"Using line: {self.line.name}")
        info(f"Using stop: {self.stop.name}")
        
        # Authenticate as passenger
        self.client.force_authenticate(user=self.user)
        
        return True
    
    def test_device_token_registration(self):
        """Test device token registration."""
        header("Testing Device Token Registration")
        
        # Register an FCM token
        token_data = {
            'token': 'test_fcm_token_12345',
            'device_type': 'android'
        }
        
        response = self.client.post('/api/v1/notifications/device-tokens/', token_data, format='json')
        
        if response.status_code == 201:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if 'id' in data:
                success(f"Device token registered with ID: {data['id']}")
            
            info(f"Device type: {data.get('device_type')}")
            info(f"Active: {data.get('is_active')}")
            
            # Test listing tokens
            response = self.client.get('/api/v1/notifications/device-tokens/')
            if response.status_code == 200:
                success(f"Retrieved {len(response.data.get('results', []))} device tokens")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_notification_preferences(self):
        """Test notification preferences."""
        header("Testing Notification Preferences")
        
        # Create preference for arrival notifications
        preference_data = {
            'notification_type': 'arrival',
            'channels': ['in_app', 'push'],
            'enabled': True,
            'minutes_before_arrival': 15,
            'quiet_hours_start': '22:00',
            'quiet_hours_end': '07:00',
            'favorite_stop_ids': [str(self.stop.id)],
            'favorite_line_ids': [str(self.line.id)]
        }
        
        response = self.client.post('/api/v1/notifications/preferences/', preference_data, format='json')
        
        if response.status_code in [200, 201]:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if 'id' in data:
                success(f"Preference created with ID: {data['id']}")
                self.preference_id = data['id']
            
            info(f"Notification type: {data.get('notification_type')}")
            info(f"Channels: {', '.join(data.get('channels', []))}")
            info(f"Minutes before arrival: {data.get('minutes_before_arrival')}")
            
            # Test updating preference
            update_data = {'minutes_before_arrival': 10}
            response = self.client.patch(f'/api/v1/notifications/preferences/{self.preference_id}/', update_data, format='json')
            
            if response.status_code == 200:
                success("Preference updated successfully")
            
            # Test getting preference by type
            response = self.client.get('/api/v1/notifications/preferences/by_type/?type=arrival')
            if response.status_code == 200:
                success("Retrieved preference by type")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_notification_creation(self):
        """Test notification creation."""
        header("Testing Notification Creation")
        
        # Create a test notification
        notification_data = {
            'notification_type': 'system',
            'title': 'Test Notification',
            'message': 'This is a test notification',
            'channel': 'in_app',
            'data': {'test_key': 'test_value'}
        }
        
        response = self.client.post('/api/v1/notifications/notifications/', notification_data, format='json')
        
        if response.status_code == 201:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if 'id' in data:
                success(f"Notification created with ID: {data['id']}")
                self.notification_id = data['id']
            else:
                # For created notifications through service, get the latest one
                latest = Notification.objects.filter(user=self.user).order_by('-created_at').first()
                if latest:
                    self.notification_id = str(latest.id)
                    success(f"Found created notification with ID: {self.notification_id}")
            
            info(f"Title: {data.get('title')}")
            info(f"Channel: {data.get('channel')}")
            
            # Test listing notifications
            response = self.client.get('/api/v1/notifications/notifications/')
            if response.status_code == 200:
                success(f"Retrieved {len(response.data.get('results', []))} notifications")
            
            # Test unread count
            response = self.client.get('/api/v1/notifications/notifications/unread_count/')
            if response.status_code == 200:
                success(f"Unread count: {response.data.get('count')}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_mark_notifications_read(self):
        """Test marking notifications as read."""
        header("Testing Mark Notifications as Read")
        
        if not hasattr(self, 'notification_id'):
            info("No notification to test with")
            return False
        
        # Mark single notification as read
        response = self.client.post(f'/api/v1/notifications/notifications/{self.notification_id}/mark_read/')
        
        if response.status_code == 200:
            success("Single notification marked as read")
            
            # Verify it's marked as read
            if response.data.get('is_read'):
                success("Notification is_read = True")
            
            # Test mark all as read
            response = self.client.post('/api/v1/notifications/notifications/mark_all_read/')
            if response.status_code == 200:
                success(f"Marked all notifications as read: {response.data.get('message')}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_arrival_notification_scheduling(self):
        """Test scheduling arrival notifications."""
        header("Testing Arrival Notification Scheduling")
        
        # Create an active trip
        trip = Trip.objects.create(
            bus=self.bus,
            driver=self.driver,
            line=self.line,
            start_time=timezone.now()
        )
        
        # Create location update near the stop
        LocationUpdate.objects.create(
            bus=self.bus,
            latitude=float(self.stop.latitude) - 0.001,  # Slightly before the stop
            longitude=float(self.stop.longitude),
            speed=30.0,
            trip_id=trip.id,
            line=self.line
        )
        
        # Schedule arrival notification
        arrival_data = {
            'bus_id': str(self.bus.id),
            'stop_id': str(self.stop.id),
            'estimated_arrival': (timezone.now() + timedelta(minutes=20)).isoformat(),
            'trip_id': str(trip.id)
        }
        
        response = self.client.post('/api/v1/notifications/notifications/schedule_arrival/', arrival_data, format='json')
        
        if response.status_code in [200, 201]:
            success(f"Status: {response.status_code}")
            
            if response.status_code == 201:
                data = response.data
                success(f"Scheduled notification ID: {data.get('id')}")
                info(f"Scheduled for: {data.get('scheduled_for')}")
                
                # Test viewing scheduled notifications
                response = self.client.get('/api/v1/notifications/schedules/')
                if response.status_code == 200:
                    success(f"Retrieved {len(response.data.get('results', []))} scheduled notifications")
            else:
                info("Notification sent immediately (arrival too soon)")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_system_notifications(self):
        """Test system-wide notifications (admin only)."""
        header("Testing System Notifications")
        
        # Create admin user
        admin = User.objects.filter(is_staff=True).first()
        if not admin:
            admin = User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass123'
            )
        
        self.client.force_authenticate(user=admin)
        
        # Test delay notification
        delay_data = {
            'bus_id': str(self.bus.id),
            'line_id': str(self.line.id),
            'delay_minutes': 15,
            'reason': 'Traffic congestion'
        }
        
        response = self.client.post('/api/v1/notifications/system/notify_delay/', delay_data, format='json')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            info(f"Message: {response.data.get('message')}")
            
            # Switch back to regular user
            self.client.force_authenticate(user=self.user)
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            
            # Switch back to regular user
            self.client.force_authenticate(user=self.user)
            
            return False
    
    def test_notification_filters(self):
        """Test notification filtering."""
        header("Testing Notification Filters")
        
        # Test filtering by type
        response = self.client.get('/api/v1/notifications/notifications/?notification_type=system')
        
        if response.status_code == 200:
            success("Filtered by notification type")
            info(f"Found {len(response.data.get('results', []))} system notifications")
        
        # Test filtering by read status
        response = self.client.get('/api/v1/notifications/notifications/?is_read=false')
        
        if response.status_code == 200:
            success("Filtered by read status")
            info(f"Found {len(response.data.get('results', []))} unread notifications")
        
        # Test search
        response = self.client.get('/api/v1/notifications/notifications/?search=test')
        
        if response.status_code == 200:
            success("Search functionality working")
            info(f"Found {len(response.data.get('results', []))} notifications matching 'test'")
        
        return True
    
    def run_all_tests(self):
        """Run all notification tests."""
        print(f"\n{BLUE}DZ Bus Tracker - Smart Notifications Test{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        if not self.setup_test_data():
            error("Failed to setup test data")
            return
        
        tests_passed = 0
        tests_total = 7
        
        # Run tests
        if self.test_device_token_registration():
            tests_passed += 1
        
        if self.test_notification_preferences():
            tests_passed += 1
        
        if self.test_notification_creation():
            tests_passed += 1
        
        if self.test_mark_notifications_read():
            tests_passed += 1
        
        if self.test_arrival_notification_scheduling():
            tests_passed += 1
        
        if self.test_system_notifications():
            tests_passed += 1
        
        if self.test_notification_filters():
            tests_passed += 1
        
        # Summary
        header("Test Summary")
        print(f"Tests passed: {tests_passed}/{tests_total}")
        
        if tests_passed == tests_total:
            success("All tests passed!")
        else:
            error(f"{tests_total - tests_passed} tests failed")

if __name__ == '__main__':
    tester = SmartNotificationTester()
    tester.run_all_tests()