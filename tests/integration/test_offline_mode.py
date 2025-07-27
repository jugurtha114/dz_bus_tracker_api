#!/usr/bin/env python3
"""
Test the Offline Mode features and API endpoints.
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
from apps.lines.models import Line, Stop, Schedule
from apps.offline_mode.models import CacheConfiguration, UserCache
from apps.offline_mode.services import OfflineModeService

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

class OfflineModeTester:
    def __init__(self):
        self.client = APIClient()
        self.user = None
        
    def setup_test_data(self):
        """Setup test data for offline mode."""
        header("Setting Up Test Data")
        
        # Get or create a test user
        self.user = User.objects.filter(user_type='passenger').first()
        if not self.user:
            self.user = User.objects.create_user(
                email='offline_test@example.com',
                password='testpass123',
                first_name='Offline',
                last_name='Tester',
                user_type='passenger'
            )
            success(f"Created test user: {self.user.email}")
        else:
            info(f"Using existing user: {self.user.email}")
        
        # Check if we have necessary data
        lines_count = Line.objects.filter(is_active=True).count()
        stops_count = Stop.objects.filter(is_active=True).count()
        buses_count = Bus.objects.filter(status='active').count()
        
        info(f"Active lines: {lines_count}")
        info(f"Active stops: {stops_count}")
        info(f"Active buses: {buses_count}")
        
        if lines_count == 0 or stops_count == 0:
            error("Missing required test data (lines or stops)")
            return False
        
        # Authenticate as user
        self.client.force_authenticate(user=self.user)
        
        return True
    
    def test_cache_configuration(self):
        """Test cache configuration endpoint."""
        header("Testing Cache Configuration")
        
        response = self.client.get('/api/v1/offline/config/current/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            config_fields = [
                'name', 'cache_duration_hours', 'max_cache_size_mb',
                'cache_lines', 'cache_stops', 'cache_schedules',
                'auto_sync_on_connect', 'sync_interval_minutes'
            ]
            
            for field in config_fields:
                if field in data:
                    info(f"{field}: {data[field]}")
                else:
                    error(f"Missing field: {field}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_cache_status(self):
        """Test user cache status."""
        header("Testing Cache Status")
        
        response = self.client.get('/api/v1/offline/cache/status/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            info(f"Last sync: {data.get('last_sync_at', 'Never')}")
            info(f"Cache size: {data.get('cache_size_mb', 0):.2f} MB")
            info(f"Is expired: {data.get('is_expired', True)}")
            info(f"Lines cached: {data.get('cached_lines_count', 0)}")
            info(f"Stops cached: {data.get('cached_stops_count', 0)}")
            info(f"Schedules cached: {data.get('cached_schedules_count', 0)}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_sync_data(self):
        """Test syncing offline data."""
        header("Testing Data Sync")
        
        sync_data = {'force': True}
        response = self.client.post('/api/v1/offline/cache/sync/', sync_data, format='json')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if data.get('status') == 'success':
                success("Sync completed successfully")
                
                stats = data.get('stats', {})
                info(f"Lines synced: {stats.get('lines', 0)}")
                info(f"Stops synced: {stats.get('stops', 0)}")
                info(f"Schedules synced: {stats.get('schedules', 0)}")
                info(f"Buses synced: {stats.get('buses', 0)}")
                info(f"Notifications synced: {stats.get('notifications', 0)}")
                info(f"Total cache size: {data.get('cache_size_mb', 0):.2f} MB")
            else:
                error(f"Sync status: {data.get('status')}")
                error(f"Message: {data.get('message')}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_cached_data_access(self):
        """Test accessing cached data."""
        header("Testing Cached Data Access")
        
        # Test lines
        response = self.client.get('/api/v1/offline/data/lines/')
        if response.status_code == 200:
            lines = response.data.get('results', [])
            success(f"Cached lines: {len(lines)}")
            if lines:
                info(f"First line: {lines[0].get('name', 'Unknown')}")
        else:
            error(f"Failed to get cached lines: {response.status_code}")
        
        # Test stops
        response = self.client.get('/api/v1/offline/data/stops/')
        if response.status_code == 200:
            stops = response.data.get('results', [])
            success(f"Cached stops: {len(stops)}")
            if stops:
                info(f"First stop: {stops[0].get('name', 'Unknown')}")
        else:
            error(f"Failed to get cached stops: {response.status_code}")
        
        # Test schedules
        response = self.client.get('/api/v1/offline/data/schedules/')
        if response.status_code == 200:
            schedules = response.data.get('results', [])
            success(f"Cached schedules: {len(schedules)}")
        else:
            error(f"Failed to get cached schedules: {response.status_code}")
        
        # Test buses
        response = self.client.get('/api/v1/offline/data/buses/')
        if response.status_code == 200:
            buses = response.data.get('results', [])
            success(f"Cached buses: {len(buses)}")
            if buses:
                info(f"First bus: {buses[0].get('bus_number', 'Unknown')}")
        else:
            error(f"Failed to get cached buses: {response.status_code}")
        
        # Test specific data request
        request_data = {
            'data_type': 'line',
            'data_id': None  # Get all lines
        }
        response = self.client.post('/api/v1/offline/data/get_data/', request_data, format='json')
        
        if response.status_code == 200:
            success("Generic data request successful")
        
        return True
    
    def test_sync_queue(self):
        """Test sync queue operations."""
        header("Testing Sync Queue")
        
        # Queue an offline action
        queue_data = {
            'action_type': 'create',
            'model_name': 'FavoriteStop',
            'data': {
                'stop_id': 'test-stop-id',
                'name': 'Test Favorite Stop'
            },
            'priority': 1
        }
        
        response = self.client.post('/api/v1/offline/sync-queue/queue_action/', queue_data, format='json')
        
        if response.status_code == 201:
            success(f"Status: {response.status_code}")
            data = response.data
            
            info(f"Queue item ID: {data.get('id')}")
            info(f"Action: {data.get('action_type')} {data.get('model_name')}")
            info(f"Status: {data.get('status')}")
            info(f"Priority: {data.get('priority')}")
            
            # Get pending items
            response = self.client.get('/api/v1/offline/sync-queue/pending/')
            if response.status_code == 200:
                pending = response.data.get('results', [])
                success(f"Pending sync items: {len(pending)}")
            
            # Process queue
            response = self.client.post('/api/v1/offline/sync-queue/process/')
            if response.status_code == 200:
                result = response.data
                success("Queue processed")
                info(f"Items synced: {result.get('completed', 0)}")
                info(f"Items failed: {result.get('failed', 0)}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_cache_statistics(self):
        """Test cache statistics."""
        header("Testing Cache Statistics")
        
        response = self.client.get('/api/v1/offline/cache/statistics/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            info(f"Cache size: {data.get('cache_size_mb', 0):.2f} MB")
            info(f"Last sync: {data.get('last_sync', 'Never')}")
            info(f"Is expired: {data.get('is_expired', True)}")
            info(f"Total items: {data.get('total_items', 0)}")
            
            # Item counts
            item_counts = data.get('item_counts', {})
            for item_type, count in item_counts.items():
                info(f"  {item_type}: {count}")
            
            # Sync queue stats
            sync_queue = data.get('sync_queue', {})
            info(f"Sync queue - Pending: {sync_queue.get('pending', 0)}")
            info(f"Sync queue - Completed: {sync_queue.get('completed', 0)}")
            info(f"Sync queue - Failed: {sync_queue.get('failed', 0)}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_offline_logs(self):
        """Test offline logs."""
        header("Testing Offline Logs")
        
        response = self.client.get('/api/v1/offline/logs/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            logs = data.get('results', [])
            info(f"Total logs: {data.get('count', 0)}")
            
            # Show recent logs
            for log in logs[:5]:
                info(f"{log['log_type']} - {log['message']}")
            
            # Get log summary
            response = self.client.get('/api/v1/offline/logs/summary/')
            if response.status_code == 200:
                summary = response.data
                success("Log summary retrieved")
                
                for log_type, details in summary.items():
                    if details['count'] > 0:
                        info(f"{details['label']}: {details['count']}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_clear_cache(self):
        """Test clearing cache."""
        header("Testing Cache Clear")
        
        response = self.client.post('/api/v1/offline/cache/clear/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            success(response.data.get('message', 'Cache cleared'))
            
            # Verify cache is empty
            response = self.client.get('/api/v1/offline/cache/status/')
            if response.status_code == 200:
                data = response.data
                info(f"Cache size after clear: {data.get('cache_size_mb', 0):.2f} MB")
                info(f"Lines cached: {data.get('cached_lines_count', 0)}")
                info(f"Stops cached: {data.get('cached_stops_count', 0)}")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def run_all_tests(self):
        """Run all offline mode tests."""
        print(f"\n{BLUE}DZ Bus Tracker - Offline Mode Test{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        if not self.setup_test_data():
            error("Failed to setup test data")
            return
        
        tests_passed = 0
        tests_total = 8
        
        # Run tests
        if self.test_cache_configuration():
            tests_passed += 1
        
        if self.test_cache_status():
            tests_passed += 1
        
        if self.test_sync_data():
            tests_passed += 1
        
        if self.test_cached_data_access():
            tests_passed += 1
        
        if self.test_sync_queue():
            tests_passed += 1
        
        if self.test_cache_statistics():
            tests_passed += 1
        
        if self.test_offline_logs():
            tests_passed += 1
        
        if self.test_clear_cache():
            tests_passed += 1
        
        # Summary
        header("Test Summary")
        print(f"Tests passed: {tests_passed}/{tests_total}")
        
        if tests_passed == tests_total:
            success("All tests passed!")
        else:
            error(f"{tests_total - tests_passed} tests failed")

if __name__ == '__main__':
    tester = OfflineModeTester()
    tester.run_all_tests()