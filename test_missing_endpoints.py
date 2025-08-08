#!/usr/bin/env python3
"""
Test for missing API endpoints discovered during integration testing
"""

import requests
import json
from typing import Dict, List, Any

class EndpointTester:
    def __init__(self, base_url: str = "http://localhost:8009"):
        self.base_url = base_url
        self.driver_token = None
        self.admin_token = None
    
    def authenticate_user(self, email: str, password: str) -> str:
        """Authenticate user and return access token"""
        try:
            response = requests.post(f"{self.base_url}/api/token/", json={
                "email": email,
                "password": password
            })
            if response.status_code == 200:
                return response.json()['access']
            else:
                print(f"Authentication failed for {email}: {response.text}")
                return None
        except Exception as e:
            print(f"Authentication error for {email}: {e}")
            return None
    
    def setup_authentication(self):
        """Set up authentication tokens for driver and admin"""
        print("🔐 Setting up authentication...")
        self.driver_token = self.authenticate_user("rachid.driver@dzbus.com", "99999999.")
        self.admin_token = self.authenticate_user("jugu@jugu.com", "99999999.")
        
        if self.driver_token:
            print("✅ Driver authentication successful")
        else:
            print("❌ Driver authentication failed")
            
        if self.admin_token:
            print("✅ Admin authentication successful")
        else:
            print("❌ Admin authentication failed")
    
    def test_endpoint(self, endpoint: str, token: str, method: str = "GET") -> Dict[str, Any]:
        """Test a single endpoint"""
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json={})
            else:
                response = requests.request(method, url, headers=headers)
                
            return {
                "endpoint": endpoint,
                "status_code": response.status_code,
                "accessible": response.status_code < 400,
                "response_size": len(response.text),
                "has_data": "count" in response.text or "results" in response.text or len(response.text) > 100
            }
        except Exception as e:
            return {
                "endpoint": endpoint,
                "status_code": 0,
                "accessible": False,
                "error": str(e)
            }
    
    def test_driver_endpoints(self) -> List[Dict[str, Any]]:
        """Test all driver-specific endpoints"""
        print("\n🚗 Testing Driver-specific endpoints...")
        
        driver_endpoints = [
            # Core driver functionality
            "/api/v1/drivers/drivers/",
            "/api/v1/drivers/drivers/profile/",
            
            # Trip management
            "/api/v1/tracking/trips/",
            "/api/v1/tracking/locations/",
            "/api/v1/tracking/passenger-counts/",
            
            # Bus management
            "/api/v1/buses/buses/",
            "/api/v1/buses/locations/",
            
            # Performance tracking
            "/api/v1/tracking/driver-performance/",
            "/api/v1/tracking/driver-currency/",
            
            # Routes and lines
            "/api/v1/lines/lines/",
            "/api/v1/lines/stops/",
            "/api/v1/lines/schedules/",
            
            # Notifications
            "/api/v1/notifications/notifications/",
            "/api/v1/notifications/device-tokens/",
        ]
        
        results = []
        for endpoint in driver_endpoints:
            result = self.test_endpoint(endpoint, self.driver_token)
            results.append(result)
            status = "✅" if result["accessible"] else "❌"
            print(f"{status} {endpoint} - Status: {result['status_code']}")
        
        return results
    
    def test_admin_endpoints(self) -> List[Dict[str, Any]]:
        """Test all admin-specific endpoints"""
        print("\n👑 Testing Admin-specific endpoints...")
        
        admin_endpoints = [
            # User management
            "/api/v1/accounts/users/",
            "/api/v1/accounts/profiles/",
            
            # Driver management
            "/api/v1/drivers/drivers/",
            
            # Fleet management
            "/api/v1/buses/buses/",
            "/api/v1/lines/lines/",
            
            # System monitoring
            "/api/v1/tracking/driver-performance/",
            "/api/v1/tracking/trips/",
            "/api/v1/tracking/locations/",
            
            # Gamification management
            "/api/v1/gamification/achievements/",
            "/api/v1/gamification/transactions/",
            "/api/v1/gamification/virtual-currency/",
            
            # Notifications management
            "/api/v1/notifications/notifications/",
            "/api/v1/notifications/schedules/",
        ]
        
        results = []
        for endpoint in admin_endpoints:
            result = self.test_endpoint(endpoint, self.admin_token)
            results.append(result)
            status = "✅" if result["accessible"] else "❌"
            print(f"{status} {endpoint} - Status: {result['status_code']}")
        
        return results
    
    def identify_missing_endpoints(self, driver_results: List[Dict], admin_results: List[Dict]):
        """Identify potentially missing or problematic endpoints"""
        print("\n🔍 Analyzing endpoint coverage...")
        
        # Check for endpoints that return no data
        empty_endpoints = []
        for result in driver_results + admin_results:
            if result["accessible"] and not result.get("has_data", False):
                empty_endpoints.append(result["endpoint"])
        
        # Common endpoints that should exist
        expected_endpoints = [
            # Driver-specific that might be missing
            "/api/v1/drivers/drivers/me/",  # Current driver profile
            "/api/v1/tracking/trips/current/",  # Current active trip
            "/api/v1/tracking/trips/start/",  # Start trip endpoint
            "/api/v1/tracking/trips/end/",  # End trip endpoint
            
            # Admin-specific that might be missing
            "/api/v1/drivers/drivers/pending/",  # Pending driver approvals
            "/api/v1/admin/dashboard/",  # Admin dashboard data
            "/api/v1/admin/statistics/",  # System statistics
        ]
        
        print(f"\n📊 Results Summary:")
        print(f"Driver endpoints tested: {len(driver_results)}")
        print(f"Admin endpoints tested: {len(admin_results)}")
        print(f"Endpoints with no data: {len(empty_endpoints)}")
        
        if empty_endpoints:
            print("\n⚠️ Endpoints returning empty results:")
            for endpoint in empty_endpoints:
                print(f"  - {endpoint}")
        
        print("\n🔎 Potentially missing endpoints to implement:")
        for endpoint in expected_endpoints:
            print(f"  - {endpoint}")
        
        return {
            "empty_endpoints": empty_endpoints,
            "suggested_endpoints": expected_endpoints
        }

def main():
    print("🚀 Starting comprehensive API endpoint testing...")
    
    tester = EndpointTester()
    tester.setup_authentication()
    
    if not tester.driver_token or not tester.admin_token:
        print("❌ Cannot proceed without authentication tokens")
        return
    
    # Test all endpoints
    driver_results = tester.test_driver_endpoints()
    admin_results = tester.test_admin_endpoints()
    
    # Analyze results
    missing_info = tester.identify_missing_endpoints(driver_results, admin_results)
    
    print("\n🎯 Testing completed successfully!")
    print("Check the results above for any endpoints that might need implementation or fixes.")

if __name__ == "__main__":
    main()