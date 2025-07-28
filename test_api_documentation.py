#!/usr/bin/env python
"""
Test script to verify API documentation and endpoints work correctly.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def test_api_endpoints_accessibility():
    """Test that our documented endpoints are accessible."""
    print("🔍 Testing Driver Currency API Documentation & Endpoints")
    print("=" * 60)
    
    # Create test driver user
    try:
        driver_user = User.objects.get(email='api_test_driver@example.com')
        print(f"✅ Using existing driver user: {driver_user.email}")
    except User.DoesNotExist:
        driver_user = User.objects.create_user(
            email='api_test_driver@example.com',
            password='testpass123',
            first_name='API',
            last_name='TestDriver',
            user_type='driver'
        )
        print(f"✅ Created new driver user: {driver_user.email}")
    
    # Create API client with authentication
    client = APIClient()
    refresh = RefreshToken.for_user(driver_user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    # Test documented endpoints
    endpoints_to_test = [
        {
            'url': '/api/v1/tracking/driver-currency/balance/',
            'name': 'Driver Currency Balance',
            'expected_status': [200, 404]  # 404 if no currency account yet
        },
        {
            'url': '/api/v1/tracking/driver-currency/transactions/',
            'name': 'Currency Transaction History',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/driver-currency/earnings_summary/',
            'name': 'Earnings Summary',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/driver-currency/leaderboard/',
            'name': 'Currency Leaderboard',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/driver-performance/',
            'name': 'Driver Performance List',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/driver-performance/leaderboard/',
            'name': 'Performance Leaderboard',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/driver-performance/my_stats/',
            'name': 'Driver Dashboard Stats',
            'expected_status': [200, 404]  # 404 if no driver profile
        },
        {
            'url': '/api/v1/tracking/premium-features/',
            'name': 'Premium Features List',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/premium-features/available/',
            'name': 'Available Features',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/user-premium-features/',
            'name': 'User Premium Features',
            'expected_status': [200]
        },
        {
            'url': '/api/v1/tracking/user-premium-features/active/',
            'name': 'Active Premium Features',
            'expected_status': [200]
        },
    ]
    
    successful_tests = 0
    total_tests = len(endpoints_to_test)
    
    for endpoint in endpoints_to_test:
        try:
            response = client.get(endpoint['url'])
            if response.status_code in endpoint['expected_status']:
                print(f"✅ {endpoint['name']}: HTTP {response.status_code}")
                successful_tests += 1
            else:
                print(f"❌ {endpoint['name']}: HTTP {response.status_code} (expected {endpoint['expected_status']})")
                if hasattr(response, 'data'):
                    print(f"   Response: {response.data}")
        except Exception as e:
            print(f"❌ {endpoint['name']}: Error - {e}")
    
    print(f"\n📊 Test Results: {successful_tests}/{total_tests} endpoints working correctly")
    
    # Test schema generation
    print(f"\n📋 Testing Schema Generation...")
    try:
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('spectacular', '--color', '--validate', stdout=out)
        print("✅ OpenAPI schema generation successful")
        
        # Check if our tags are present
        schema_content = out.getvalue()
        driver_tags = [
            'Driver Performance',
            'Driver Virtual Currency', 
            'Premium Features',
            'User Premium Features'
        ]
        
        for tag in driver_tags:
            if tag.lower() in schema_content.lower():
                print(f"✅ Found documentation tag: {tag}")
            else:
                print(f"⚠️  Documentation tag not found: {tag}")
                
    except Exception as e:
        print(f"❌ Schema generation failed: {e}")
    
    print(f"\n🎉 API Documentation Testing Complete!")

if __name__ == '__main__':
    test_api_endpoints_accessibility()