#!/usr/bin/env python3
"""
Comprehensive API testing script for DZ Bus Tracker.
Tests all API endpoints with proper authentication.
"""
import requests
import json
import sys

# API base URL
BASE_URL = "http://localhost:8007/api"

class APITester:
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        
    def authenticate(self, email, password):
        """Authenticate user and get JWT tokens."""
        print(f"\n🔐 Authenticating user: {email}")
        response = requests.post(f"{BASE_URL}/token/", json={
            "email": email,
            "password": password
        })
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access']
            self.refresh_token = data['refresh']
            print("✅ Authentication successful")
            return True
        else:
            print(f"❌ Authentication failed: {response.text}")
            return False
    
    def get_headers(self):
        """Get headers with authorization token."""
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}
    
    def test_endpoint(self, endpoint, method="GET", data=None, description=""):
        """Test a single API endpoint."""
        url = f"{BASE_URL}{endpoint}"
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"
        
        print(f"\n{description}")
        print(f"Testing: {method} {endpoint}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == "PATCH":
                response = requests.patch(url, json=data, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            
            print(f"Status: {response.status_code}")
            
            if response.status_code < 400:
                try:
                    content = response.json()
                    print(f"✅ Success: {len(str(content))} characters returned")
                    if isinstance(content, dict):
                        if 'results' in content:
                            print(f"   Found {len(content['results'])} items")
                        elif 'count' in content:
                            print(f"   Total count: {content['count']}")
                    return content
                except:
                    print(f"✅ Success: {response.text[:100]}...")
                    return response.text
            else:
                print(f"❌ Error: {response.text[:200]}")
                return None
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection refused (server not running)")
            return None
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None

def test_driver_apis():
    """Test driver-specific API endpoints."""
    tester = APITester()
    
    # Authenticate as driver
    if not tester.authenticate("rachid.driver@dzbus.com", "99999999"):
        return
    
    print("\n" + "="*60)
    print("🚗 DRIVER API TESTING")
    print("="*60)
    
    # Test driver endpoints
    tester.test_endpoint("/v1/drivers/drivers/", "GET", description="📋 Get driver list")
    
    # Test user profile
    tester.test_endpoint("/v1/accounts/users/me/", "GET", description="👤 Get current user profile")
    
    # Test buses
    tester.test_endpoint("/v1/buses/", "GET", description="🚌 Get buses list")
    
    # Test lines
    tester.test_endpoint("/v1/lines/", "GET", description="🛣️ Get bus lines")
    
    # Test tracking endpoints
    tester.test_endpoint("/v1/tracking/trips/", "GET", description="📍 Get trips")
    
    # Test gamification
    tester.test_endpoint("/v1/gamification/reputation/", "GET", description="🏆 Get reputation scores")
    tester.test_endpoint("/v1/gamification/currency/", "GET", description="💰 Get virtual currency")
    
    # Test notifications
    tester.test_endpoint("/v1/notifications/", "GET", description="📢 Get notifications")

def test_admin_apis():
    """Test admin-specific API endpoints."""
    tester = APITester()
    
    # Authenticate as admin
    if not tester.authenticate("jugu@jugu.com", "99999999"):
        return
    
    print("\n" + "="*60)
    print("⚙️ ADMIN API TESTING")
    print("="*60)
    
    # Test admin endpoints
    tester.test_endpoint("/v1/accounts/users/", "GET", description="👥 Get all users")
    tester.test_endpoint("/v1/drivers/drivers/", "GET", description="🚗 Get all drivers")
    tester.test_endpoint("/v1/buses/", "GET", description="🚌 Get all buses")
    tester.test_endpoint("/v1/lines/", "GET", description="🛣️ Get all lines")
    tester.test_endpoint("/v1/tracking/trips/", "GET", description="📍 Get all trips")

def test_public_apis():
    """Test public API endpoints (no auth required)."""
    tester = APITester()
    
    print("\n" + "="*60)
    print("🌐 PUBLIC API TESTING")
    print("="*60)
    
    # Test public endpoints
    tester.test_endpoint("/health", "GET", description="💚 Health check")
    tester.test_endpoint("/schema/", "GET", description="📋 API Schema")

def main():
    """Run comprehensive API tests."""
    print("🧪 DZ BUS TRACKER - COMPREHENSIVE API INTEGRATION TEST")
    print("=" * 80)
    
    # Test public APIs
    test_public_apis()
    
    # Test driver APIs
    test_driver_apis()
    
    # Test admin APIs
    test_admin_apis()
    
    print("\n" + "="*80)
    print("✨ COMPREHENSIVE API TESTING COMPLETED!")
    print("="*80)

if __name__ == "__main__":
    main()