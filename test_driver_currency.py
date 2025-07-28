#!/usr/bin/env python
"""
Simple test script for driver currency and premium features.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.contrib.auth import get_user_model
from apps.tracking.models import VirtualCurrency, PremiumFeature, DriverPerformanceScore
from apps.tracking.services.driver_services import DriverCurrencyService, DriverPerformanceService
from apps.drivers.models import Driver

User = get_user_model()

def test_driver_currency_system():
    """Test the driver currency system."""
    print("🚀 Testing Driver Virtual Currency System")
    print("=" * 50)
    
    # Create a test driver user
    try:
        driver_user = User.objects.get(email='test_driver@example.com')
        print(f"✅ Using existing driver user: {driver_user.email}")
    except User.DoesNotExist:
        driver_user = User.objects.create_user(
            email='test_driver@example.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type='driver'
        )
        print(f"✅ Created new driver user: {driver_user.email}")
    
    # Create driver profile if doesn't exist
    try:
        driver = Driver.objects.get(user=driver_user)
        print(f"✅ Using existing driver profile: {driver.id}")
    except Driver.DoesNotExist:
        driver = Driver.objects.create(
            user=driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        print(f"✅ Created new driver profile: {driver.id}")
    
    # Test virtual currency creation
    print("\n💰 Testing Virtual Currency...")
    currency, created = VirtualCurrency.objects.get_or_create(
        user=driver_user,
        defaults={'balance': 100}
    )
    print(f"✅ Driver currency balance: {currency.balance} coins")
    
    # Test adding currency
    print("\n💎 Testing Currency Addition...")
    DriverCurrencyService.add_driver_currency(
        driver_user,
        150,
        'route_completion',
        'Test route completion bonus'
    )
    currency.refresh_from_db()
    print(f"✅ Added 150 coins. New balance: {currency.balance} coins")
    
    # Test driver performance score
    print("\n📊 Testing Driver Performance...")
    performance = DriverPerformanceService.get_or_create_performance_score(driver)
    print(f"✅ Driver performance level: {performance.performance_level}")
    print(f"✅ Total trips: {performance.total_trips}")
    print(f"✅ On-time percentage: {performance.on_time_percentage:.1f}%")
    
    # Update performance
    DriverPerformanceService.update_trip_performance(driver, None, is_on_time=True)
    performance.refresh_from_db()
    print(f"✅ Updated performance. New trips: {performance.total_trips}")
    
    # Test premium features
    print("\n🌟 Testing Premium Features...")
    features = PremiumFeature.objects.filter(is_active=True)[:3]
    print(f"✅ Available premium features: {features.count()}")
    
    for feature in features:
        print(f"   - {feature.name}: {feature.cost_coins} coins ({feature.target_users})")
    
    # Test earnings summary
    print("\n📈 Testing Earnings Summary...")
    summary = DriverCurrencyService.get_driver_earnings_summary(driver_user, 30)
    print(f"✅ Total earned (30 days): {summary.get('total_earned', 0)} coins")
    print(f"✅ Transaction count: {summary.get('transaction_count', 0)}")
    
    # Test leaderboard
    print("\n🏆 Testing Driver Leaderboard...")
    leaderboard = DriverPerformanceService.get_driver_leaderboard(5)
    print(f"✅ Leaderboard entries: {len(leaderboard)}")
    
    for entry in leaderboard[:3]:
        print(f"   {entry['rank']}. {entry['driver_name']} - {entry['performance_level']}")
    
    print("\n🎉 Driver Currency System Test Complete!")
    print("=" * 50)


def test_api_endpoints():
    """Test API endpoints are accessible."""
    print("\n🌐 Testing API Endpoint Registration...")
    print("=" * 30)
    
    from django.urls import reverse
    from django.test import Client
    
    client = Client()
    
    # Test endpoints without authentication (should return 401/403)
    endpoints = [
        'premiumfeature-list',
        'user-premium-features-list',
        'driver-currency-balance',
    ]
    
    for endpoint in endpoints:
        try:
            url = reverse(endpoint)
            response = client.get(url)
            print(f"✅ {endpoint}: {url} -> HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint}: Error - {e}")
    
    print("\n✅ API Endpoints Test Complete!")


if __name__ == '__main__':
    test_driver_currency_system()
    test_api_endpoints()