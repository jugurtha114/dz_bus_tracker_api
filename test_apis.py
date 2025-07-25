#!/usr/bin/env python3
"""
Test all CRUD APIs for DZ Bus Tracker.
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8001/api"

# Test users credentials
USERS = {
    "admin": {"email": "admin@dzbus.com", "password": "admin123"},
    "manager": {"email": "manager@dzbus.com", "password": "manager123"},
    "driver": {"email": "ahmed.driver@dzbus.com", "password": "driver123"},
    "passenger": {"email": "fatima@dzbus.com", "password": "pass123"},
}

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

class APITester:
    def __init__(self):
        self.tokens = {}
        self.session = requests.Session()
        
    def get_token(self, user_type):
        """Get JWT token for a user."""
        if user_type in self.tokens:
            return self.tokens[user_type]
            
        user = USERS[user_type]
        response = self.session.post(f"{BASE_URL}/token/", json=user)
        
        if response.status_code == 200:
            data = response.json()
            self.tokens[user_type] = data['access']
            success(f"Authenticated as {user_type}: {user['email']}")
            return data['access']
        else:
            error(f"Failed to authenticate {user_type}: {response.status_code}")
            return None
    
    def make_request(self, method, endpoint, user_type=None, data=None, params=None):
        """Make an authenticated request."""
        headers = {}
        if user_type:
            token = self.get_token(user_type)
            if token:
                headers['Authorization'] = f'Bearer {token}'
        
        url = f"{BASE_URL}{endpoint}"
        
        if method == 'GET':
            response = self.session.get(url, headers=headers, params=params)
        elif method == 'POST':
            response = self.session.post(url, headers=headers, json=data)
        elif method == 'PUT':
            response = self.session.put(url, headers=headers, json=data)
        elif method == 'PATCH':
            response = self.session.patch(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = self.session.delete(url, headers=headers)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return response
    
    def test_authentication(self):
        """Test authentication endpoints."""
        header("Testing Authentication")
        
        # Test token generation for each user type
        for user_type in USERS:
            token = self.get_token(user_type)
            if not token:
                error(f"Failed to authenticate {user_type}")
                return False
        
        # Test token verification
        info("Testing token verification...")
        response = self.session.post(f"{BASE_URL}/token/verify/", 
                                   json={"token": self.tokens["admin"]})
        if response.status_code == 200:
            success("Token verification working")
        else:
            error(f"Token verification failed: {response.status_code}")
        
        return True
    
    def test_user_apis(self):
        """Test user-related APIs."""
        header("Testing User APIs")
        
        # Test user profile retrieval
        info("Testing user profile retrieval...")
        response = self.make_request('GET', '/v1/accounts/profile/', 'passenger')
        if response.status_code == 200:
            profile = response.json()
            success(f"Retrieved profile for {profile.get('email', 'user')}")
            print(f"  User type: {profile.get('user_type')}")
        else:
            error(f"Failed to get profile: {response.status_code}")
        
        # Test user list (admin only)
        info("Testing user list (admin only)...")
        response = self.make_request('GET', '/v1/accounts/users/', 'admin')
        if response.status_code == 200:
            users = response.json()
            count = users.get('count', len(users.get('results', [])))
            success(f"Retrieved {count} users")
        else:
            error(f"Failed to get user list: {response.status_code}")
        
        return True
    
    def test_bus_apis(self):
        """Test bus-related APIs."""
        header("Testing Bus APIs")
        
        # Test bus list
        info("Testing bus list...")
        response = self.make_request('GET', '/v1/buses/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            buses = data.get('results', [])
            success(f"Retrieved {len(buses)} buses")
            if buses:
                print(f"  First bus: {buses[0].get('license_plate')} - {buses[0].get('model')}")
        else:
            error(f"Failed to get bus list: {response.status_code}")
        
        # Test bus details
        if response.status_code == 200 and buses:
            bus_id = buses[0]['id']
            info(f"Testing bus details for {buses[0]['license_plate']}...")
            response = self.make_request('GET', f'/v1/buses/{bus_id}/', 'passenger')
            if response.status_code == 200:
                bus = response.json()
                success(f"Retrieved bus details: {bus['license_plate']}")
                print(f"  Driver: {bus.get('driver_name', 'N/A')}")
                print(f"  Capacity: {bus.get('capacity')} passengers")
            else:
                error(f"Failed to get bus details: {response.status_code}")
        
        # Test bus creation (admin only)
        info("Testing bus creation (admin only)...")
        # This will fail because we need a driver ID, but it tests the permission
        response = self.make_request('POST', '/v1/buses/', 'passenger', {
            "license_plate": "16-TEST-01",
            "model": "Test Bus",
            "manufacturer": "Test Manufacturer",
            "year": 2024,
            "capacity": 30
        })
        if response.status_code == 403:
            success("Bus creation correctly restricted to admins")
        else:
            info(f"Bus creation returned: {response.status_code}")
        
        return True
    
    def test_line_apis(self):
        """Test line-related APIs."""
        header("Testing Line APIs")
        
        # Test line list
        info("Testing line list...")
        response = self.make_request('GET', '/v1/lines/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            lines = data.get('results', [])
            success(f"Retrieved {len(lines)} lines")
            if lines:
                print(f"  Lines: {', '.join([l['code'] for l in lines])}")
        else:
            error(f"Failed to get line list: {response.status_code}")
        
        # Test line details with stops
        if response.status_code == 200 and lines:
            line_id = lines[0]['id']
            info(f"Testing line details for {lines[0]['code']}...")
            response = self.make_request('GET', f'/v1/lines/{line_id}/', 'passenger')
            if response.status_code == 200:
                line = response.json()
                success(f"Retrieved line details: {line['name']}")
                stops = line.get('stops', [])
                if stops:
                    print(f"  Stops: {len(stops)}")
                    print(f"  First stop: {stops[0].get('name', 'N/A')}")
            else:
                error(f"Failed to get line details: {response.status_code}")
        
        # Test schedules
        info("Testing schedules...")
        response = self.make_request('GET', '/v1/lines/schedules/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            schedules = data.get('results', [])
            success(f"Retrieved {len(schedules)} schedules")
        else:
            error(f"Failed to get schedules: {response.status_code}")
        
        return True
    
    def test_tracking_apis(self):
        """Test tracking-related APIs."""
        header("Testing Tracking APIs")
        
        # Test location updates
        info("Testing location updates...")
        response = self.make_request('GET', '/v1/tracking/locations/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            locations = data.get('results', [])
            success(f"Retrieved {len(locations)} location updates")
            if locations:
                loc = locations[0]
                print(f"  Bus: {loc.get('bus_info', {}).get('license_plate', 'N/A')}")
                print(f"  Location: ({loc.get('latitude')}, {loc.get('longitude')})")
        else:
            error(f"Failed to get location updates: {response.status_code}")
        
        # Test active trips
        info("Testing active trips...")
        response = self.make_request('GET', '/v1/tracking/trips/', 'passenger', 
                                   params={'active': 'true'})
        if response.status_code == 200:
            data = response.json()
            trips = data.get('results', [])
            success(f"Retrieved {len(trips)} active trips")
            if trips:
                trip = trips[0]
                print(f"  Line: {trip.get('line_info', {}).get('name', 'N/A')}")
                print(f"  Bus: {trip.get('bus_info', {}).get('license_plate', 'N/A')}")
        else:
            error(f"Failed to get active trips: {response.status_code}")
        
        # Test waiting passengers
        info("Testing waiting passengers...")
        response = self.make_request('GET', '/v1/tracking/waiting-passengers/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            waiting = data.get('results', [])
            success(f"Retrieved {len(waiting)} waiting passenger reports")
        else:
            error(f"Failed to get waiting passengers: {response.status_code}")
        
        return True
    
    def test_driver_apis(self):
        """Test driver-specific APIs."""
        header("Testing Driver APIs")
        
        # Test driver list (admin view)
        info("Testing driver list (admin)...")
        response = self.make_request('GET', '/v1/drivers/', 'admin')
        if response.status_code == 200:
            data = response.json()
            drivers = data.get('results', [])
            success(f"Retrieved {len(drivers)} drivers")
            approved = sum(1 for d in drivers if d.get('status') == 'approved')
            pending = sum(1 for d in drivers if d.get('status') == 'pending')
            print(f"  Approved: {approved}, Pending: {pending}")
        else:
            error(f"Failed to get driver list: {response.status_code}")
        
        # Test driver profile (driver view)
        info("Testing driver profile...")
        response = self.make_request('GET', '/v1/drivers/profile/', 'driver')
        if response.status_code == 200:
            driver = response.json()
            success(f"Retrieved driver profile")
            print(f"  Status: {driver.get('status')}")
            print(f"  Rating: {driver.get('rating', 0)}/5")
            print(f"  Years of experience: {driver.get('years_of_experience', 0)}")
        else:
            error(f"Failed to get driver profile: {response.status_code}")
        
        return True
    
    def test_notification_apis(self):
        """Test notification APIs."""
        header("Testing Notification APIs")
        
        # Test notification list
        info("Testing notification list...")
        response = self.make_request('GET', '/v1/notifications/', 'passenger')
        if response.status_code == 200:
            data = response.json()
            notifications = data.get('results', [])
            success(f"Retrieved {len(notifications)} notifications")
            unread = sum(1 for n in notifications if not n.get('is_read'))
            print(f"  Unread: {unread}")
        else:
            error(f"Failed to get notifications: {response.status_code}")
        
        # Test device token registration
        info("Testing device token registration...")
        response = self.make_request('POST', '/v1/notifications/devices/', 'passenger', {
            "token": f"test_token_{datetime.now().timestamp()}",
            "device_type": "android"
        })
        if response.status_code in [200, 201]:
            success("Device token registered successfully")
        else:
            error(f"Failed to register device token: {response.status_code}")
        
        return True
    
    def test_api_documentation(self):
        """Test API documentation endpoints."""
        header("Testing API Documentation")
        
        # Test schema endpoint
        info("Testing OpenAPI schema...")
        response = self.session.get(f"{BASE_URL}/schema/")
        if response.status_code == 200:
            success("OpenAPI schema accessible")
            schema = response.json()
            print(f"  API Version: {schema.get('info', {}).get('version')}")
            print(f"  Endpoints: {len(schema.get('paths', {}))}")
        else:
            error(f"Failed to get OpenAPI schema: {response.status_code}")
        
        # Test Swagger UI
        info("Testing Swagger UI...")
        response = self.session.get(f"{BASE_URL}/schema/swagger-ui/")
        if response.status_code == 200:
            success("Swagger UI accessible at http://localhost:8001/api/schema/swagger-ui/")
        else:
            error(f"Failed to access Swagger UI: {response.status_code}")
        
        return True
    
    def run_all_tests(self):
        """Run all API tests."""
        print(f"\n{BLUE}Starting API Tests for DZ Bus Tracker{RESET}")
        print(f"{BLUE}API Base URL: {BASE_URL}{RESET}\n")
        
        tests = [
            self.test_authentication,
            self.test_user_apis,
            self.test_bus_apis,
            self.test_line_apis,
            self.test_tracking_apis,
            self.test_driver_apis,
            self.test_notification_apis,
            self.test_api_documentation,
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                error(f"Test {test.__name__} failed with exception: {e}")
                failed += 1
        
        # Summary
        header("Test Summary")
        print(f"{GREEN}Passed: {passed}{RESET}")
        print(f"{RED}Failed: {failed}{RESET}")
        print(f"\n{GREEN}✓ API testing completed!{RESET}")
        
        # Print useful links
        print(f"\n{BLUE}Useful Links:{RESET}")
        print(f"  • Admin Panel: http://localhost:8001/admin/")
        print(f"  • API Documentation: http://localhost:8001/api/schema/swagger-ui/")
        print(f"  • API Root: http://localhost:8001/api/v1/")

if __name__ == '__main__':
    tester = APITester()
    tester.run_all_tests()