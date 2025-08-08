#!/usr/bin/env python3
"""
Test admin-specific API endpoints.
"""
import requests
import json

BASE_URL = "http://localhost:8007/api"
ADMIN_TOKEN = None

def authenticate_admin():
    """Authenticate as admin and get token."""
    global ADMIN_TOKEN
    response = requests.post(f"{BASE_URL}/token/", json={
        "email": "jugu@jugu.com",
        "password": "99999999"
    })
    
    if response.status_code == 200:
        ADMIN_TOKEN = response.json()['access']
        print("✅ Admin authentication successful")
        return True
    else:
        print(f"❌ Admin authentication failed: {response.text}")
        return False

def test_admin_endpoint(endpoint, description):
    """Test a single admin endpoint."""
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
        print(f"\n{description}")
        print(f"Endpoint: {endpoint}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'results' in data:
                    print(f"✅ Success - {len(data['results'])} items found")
                elif isinstance(data, list):
                    print(f"✅ Success - {len(data)} items found") 
                else:
                    print(f"✅ Success - Response received")
            except:
                print(f"✅ Success - {len(response.text)} characters")
        else:
            print(f"❌ Error: {response.text[:150]}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def main():
    """Test admin endpoints."""
    print("🛠️ ADMIN API ENDPOINT TESTING")
    print("=" * 50)
    
    if not authenticate_admin():
        return
    
    # Test admin-accessible endpoints
    test_admin_endpoint("/v1/accounts/users/", "👥 List all users")
    test_admin_endpoint("/v1/drivers/drivers/", "🚗 List all drivers")  
    test_admin_endpoint("/v1/buses/", "🚌 List all buses")
    test_admin_endpoint("/v1/lines/", "🛣️ List all lines")
    test_admin_endpoint("/v1/tracking/trips/", "📍 List all trips")
    test_admin_endpoint("/v1/gamification/reputation/", "🏆 List reputation scores")
    test_admin_endpoint("/v1/notifications/", "📢 List notifications")
    
    # Test current admin user profile
    test_admin_endpoint("/v1/accounts/users/me/", "👤 Get admin profile")
    
    print("\n" + "=" * 50)
    print("✨ Admin API testing completed!")

if __name__ == "__main__":
    main()