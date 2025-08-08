#!/usr/bin/env python3
"""
Test script to verify API endpoints are working properly.
"""
import requests
import json
import sys

# API base URL
BASE_URL = "http://localhost:8007/api"

def test_endpoint(endpoint, method="GET", data=None, headers=None):
    """Test a single API endpoint."""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=10)
        
        print(f"✅ {method} {endpoint} - Status: {response.status_code}")
        if response.status_code < 400:
            try:
                content = response.json()
                print(f"   Response: {json.dumps(content, indent=2)[:200]}...")
            except:
                print(f"   Response: {response.text[:200]}...")
        else:
            print(f"   Error: {response.text[:200]}")
        return response
    except requests.exceptions.ConnectionError:
        print(f"❌ {method} {endpoint} - Connection refused (server not running)")
        return None
    except Exception as e:
        print(f"❌ {method} {endpoint} - Error: {str(e)}")
        return None

def test_authentication():
    """Test authentication endpoints."""
    print("\n🔐 Testing Authentication Endpoints:")
    
    # Test token endpoint
    test_endpoint("/token/", "POST", {
        "email": "rachid.driver@dzbus.com", 
        "password": "99999999"
    })
    
    # Test refresh token
    test_endpoint("/token/refresh/", "POST")

def test_driver_endpoints():
    """Test driver-related endpoints."""
    print("\n🚗 Testing Driver Endpoints:")
    
    # Test driver list
    test_endpoint("/v1/drivers/drivers/")
    
    # Test driver registration
    test_endpoint("/v1/drivers/register/", "POST", {
        "email": "test@example.com",
        "password": "testpass123",
        "first_name": "Test",
        "last_name": "Driver"
    })

def test_general_endpoints():
    """Test general API endpoints."""
    print("\n📊 Testing General Endpoints:")
    
    # Test API health
    test_endpoint("/health/")
    
    # Test buses
    test_endpoint("/v1/buses/")
    
    # Test lines
    test_endpoint("/v1/lines/")

def main():
    """Run all API tests."""
    print("🧪 DZ Bus Tracker API Integration Test")
    print("=====================================")
    
    test_general_endpoints()
    test_authentication()
    test_driver_endpoints()
    
    print("\n✨ API testing completed!")

if __name__ == "__main__":
    main()