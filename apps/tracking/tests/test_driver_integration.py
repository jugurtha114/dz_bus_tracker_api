"""
Integration tests for the complete driver currency workflow.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import (
    CurrencyTransaction,
    DriverPerformanceScore,
    PremiumFeature,
    Trip,
    UserPremiumFeature,
    VirtualCurrency,
    WaitingCountReport,
)
from apps.tracking.services.driver_services import (
    DriverCurrencyService,
    DriverPerformanceService,
    PremiumFeatureService,
)

User = get_user_model()


class DriverWorkflowIntegrationTest(TestCase):
    """Test complete driver workflow from registration to premium purchases."""

    def setUp(self):
        """Set up comprehensive test scenario."""
        # Create test users
        self.driver_user = User.objects.create_user(
            email='integration_driver@test.com',
            password='testpass123',
            first_name='Integration',
            last_name='Driver',
            user_type='driver'
        )
        
        self.passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Passenger',
            user_type='passenger'
        )
        
        # Create driver profile
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        
        # Create test line and stops
        self.line = Line.objects.create(
            code='TEST01',
            name='Test Line',
            description='Test route for integration testing'
        )
        
        self.start_stop = Stop.objects.create(
            name='Start Stop',
            latitude=36.7538,
            longitude=3.0588,
            address='Test Address 1'
        )
        
        self.end_stop = Stop.objects.create(
            name='End Stop',
            latitude=36.7548,
            longitude=3.0598,
            address='Test Address 2'
        )
        
        # Create test bus
        self.bus = Bus.objects.create(
            license_plate='TEST-123',
            driver=self.driver,
            model='Test Bus Model',
            capacity=50,
            manufacturer='Test Manufacturer',
            year=2020
        )
        
        # Create premium features
        self.premium_feature = PremiumFeature.objects.create(
            name='Integration Test Feature',
            feature_type='route_analytics',
            description='Test feature for integration testing',
            cost_coins=500,
            duration_days=30,
            target_users='drivers',
            required_level='rookie'
        )

    def test_complete_driver_journey(self):
        """Test complete driver journey from new driver to premium user."""
        
        # Step 1: New driver starts with welcome currency
        print("🚀 Step 1: Driver Registration & Initial Setup")
        
        # Initialize driver performance
        performance = DriverPerformanceService.get_or_create_performance_score(self.driver)
        self.assertEqual(performance.performance_level, 'rookie')
        self.assertEqual(performance.total_trips, 0)
        
        # Give welcome bonus
        DriverCurrencyService.add_driver_currency(
            self.driver_user, 100, 'admin_adjustment', 'Welcome bonus'
        )
        
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        self.assertEqual(currency.balance, 200)  # 100 default + 100 welcome
        print(f"✅ Initial currency balance: {currency.balance} coins")
        
        # Step 2: Complete multiple trips and earn performance bonuses
        print("\n🚗 Step 2: Trip Completion & Performance Building")
        
        for i in range(10):
            # Simulate completing trips
            trip = Trip.objects.create(
                bus=self.bus,
                driver=self.driver,
                line=self.line,
                start_stop=self.start_stop,
                end_stop=self.end_stop,
                start_time=timezone.now() - timedelta(hours=2),
                end_time=timezone.now() - timedelta(hours=1),
                is_completed=True
            )
            
            # 80% of trips are on-time
            is_on_time = i < 8
            DriverPerformanceService.update_trip_performance(
                self.driver, trip, is_on_time=is_on_time
            )
        
        # Check performance progression
        performance.refresh_from_db()
        self.assertEqual(performance.total_trips, 10)
        self.assertEqual(performance.on_time_trips, 8)
        self.assertEqual(performance.on_time_percentage, 80.0)
        print(f"✅ Completed {performance.total_trips} trips with {performance.on_time_percentage}% on-time")
        
        # Check currency earned from trips
        currency.refresh_from_db()
        initial_balance = currency.balance
        print(f"✅ Currency after trips: {currency.balance} coins")
        
        # Step 3: Driver verifies passenger reports and earns accuracy bonus
        print("\n📋 Step 3: Report Verification & Accuracy Building")
        
        # Create passenger waiting report
        report = WaitingCountReport.objects.create(
            stop=self.start_stop,
            bus=self.bus,
            line=self.line,
            reported_count=5,
            reporter=self.passenger_user,
            confidence_level='high'
        )
        
        # Driver verifies the report as accurate
        report.verified_by = self.driver_user
        report.actual_count = 5
        report.verification_status = 'correct'
        report.is_verified = True
        report.verified_at = timezone.now()
        report.save()
        
        # Update verification accuracy
        DriverPerformanceService.update_verification_accuracy(self.driver, was_accurate=True)
        
        performance.refresh_from_db()
        currency.refresh_from_db()
        verification_earnings = currency.balance - initial_balance
        print(f"✅ Earned {verification_earnings} coins from accurate verification")
        
        # Step 4: Performance level progression
        print("\n📈 Step 4: Performance Level Progression")
        
        # Improve performance to reach next level
        performance.total_trips = 25
        performance.on_time_trips = 20  # 80% on-time
        performance.safety_score = Decimal('90.00')
        performance.passenger_rating = Decimal('4.0')
        performance.update_performance_level()
        
        self.assertEqual(performance.performance_level, 'experienced')
        print(f"✅ Advanced to {performance.performance_level} level")
        
        # Step 5: Browse and purchase premium features
        print("\n🌟 Step 5: Premium Feature Purchase")
        
        # Check available features
        available_features = PremiumFeatureService.get_available_features_for_user(
            self.driver_user
        )
        self.assertGreater(len(available_features), 0)
        print(f"✅ Found {len(available_features)} available premium features")
        
        # Ensure sufficient balance for purchase
        if currency.balance < self.premium_feature.cost_coins:
            needed_coins = self.premium_feature.cost_coins - currency.balance
            DriverCurrencyService.add_driver_currency(
                self.driver_user, needed_coins, 'admin_adjustment', 'Test adjustment'
            )
            currency.refresh_from_db()
        
        balance_before_purchase = currency.balance
        
        # Purchase premium feature
        result = PremiumFeatureService.purchase_feature(
            self.driver_user,
            str(self.premium_feature.id)
        )
        
        self.assertTrue(result['success'])
        print(f"✅ Successfully purchased {self.premium_feature.name}")
        
        # Verify purchase
        purchase = UserPremiumFeature.objects.get(
            user=self.driver_user,
            feature=self.premium_feature
        )
        self.assertTrue(purchase.is_active)
        self.assertFalse(purchase.is_expired)
        
        currency.refresh_from_db()
        coins_spent = balance_before_purchase - currency.balance
        self.assertEqual(coins_spent, self.premium_feature.cost_coins)
        print(f"✅ Spent {coins_spent} coins, remaining balance: {currency.balance}")
        
        # Step 6: Use premium feature
        print("\n🎯 Step 6: Premium Feature Access")
        
        # Check feature access
        has_access = PremiumFeatureService.check_feature_access(
            self.driver_user,
            self.premium_feature.feature_type
        )
        self.assertTrue(has_access)
        print(f"✅ Confirmed access to {self.premium_feature.feature_type}")
        
        # Step 7: Summary statistics
        print("\n📊 Step 7: Final Statistics Summary")
        
        # Get final performance stats
        performance.refresh_from_db()
        currency.refresh_from_db()
        
        # Get earnings summary
        earnings_summary = DriverCurrencyService.get_driver_earnings_summary(
            self.driver_user, 30
        )
        
        # Get transaction history
        transactions = CurrencyTransaction.objects.filter(
            user=self.driver_user
        ).order_by('-created_at')
        
        print(f"✅ Final Performance Level: {performance.performance_level}")
        print(f"✅ Total Trips: {performance.total_trips}")
        print(f"✅ On-Time Percentage: {performance.on_time_percentage}%")
        print(f"✅ Safety Score: {performance.safety_score}")
        print(f"✅ Current Currency Balance: {currency.balance}")
        print(f"✅ Lifetime Earned: {currency.lifetime_earned}")
        print(f"✅ Lifetime Spent: {currency.lifetime_spent}")
        print(f"✅ Total Transactions: {transactions.count()}")
        print(f"✅ Active Premium Features: {UserPremiumFeature.objects.filter(user=self.driver_user, is_active=True).count()}")
        
        # Assertions for final state
        self.assertEqual(performance.performance_level, 'experienced')
        self.assertGreater(currency.lifetime_earned, 100)
        self.assertEqual(currency.lifetime_spent, self.premium_feature.cost_coins)
        self.assertGreater(transactions.count(), 5)
        
        print("\n🎉 Complete Driver Journey Test Successful!")


class DriverAPIIntegrationTest(APITestCase):
    """Test complete API workflow for drivers."""

    def setUp(self):
        """Set up test data."""
        self.driver_user = User.objects.create_user(
            email='api_driver@test.com',
            password='testpass123',
            first_name='API',
            last_name='Driver',
            user_type='driver'
        )
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000002',
            id_card_number='1234567891',
            driver_license_number='DL123457',
            years_of_experience=3,
            status='approved'
        )
        
        # Create currency account with sufficient balance
        VirtualCurrency.objects.create(
            user=self.driver_user,
            balance=2000,
            lifetime_earned=1500
        )
        
        # Create performance score
        DriverPerformanceScore.objects.create(
            driver=self.driver,
            total_trips=15,
            on_time_trips=12,
            performance_level='experienced',
            safety_score=Decimal('95.00'),
            passenger_rating=Decimal('4.2')
        )
        
        # Create premium feature
        self.feature = PremiumFeature.objects.create(
            name='API Test Feature',
            feature_type='route_analytics',
            description='Feature for API testing',
            cost_coins=600,
            duration_days=30,
            target_users='drivers',
            required_level='rookie'
        )

    def test_complete_api_workflow(self):
        """Test complete API workflow for drivers."""
        print("🌐 Testing Complete Driver API Workflow")
        
        # Authenticate as driver
        self.client.force_authenticate(user=self.driver_user)
        
        # Step 1: Get driver statistics
        print("\n📊 Step 1: Get Driver Statistics")
        response = self.client.get('/api/v1/tracking/driver-performance/my_stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        stats = response.data
        self.assertIn('performance_score', stats)
        self.assertIn('virtual_currency', stats)
        self.assertIn('available_features', stats)
        print(f"✅ Retrieved driver stats: {stats['performance_score']['performance_level']} level")
        
        # Step 2: Check currency balance
        print("\n💰 Step 2: Check Currency Balance")
        response = self.client.get('/api/v1/tracking/driver-currency/balance/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        balance_data = response.data
        self.assertEqual(balance_data['balance'], 2000)
        print(f"✅ Currency balance: {balance_data['balance']} coins")
        
        # Step 3: Get available premium features
        print("\n🌟 Step 3: Browse Premium Features")
        response = self.client.get('/api/v1/tracking/premium-features/available/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        features = response.data
        self.assertGreater(len(features), 0)
        feature_names = [f['name'] for f in features]
        self.assertIn('API Test Feature', feature_names)
        print(f"✅ Found {len(features)} available features")
        
        # Step 4: Purchase premium feature
        print("\n💳 Step 4: Purchase Premium Feature")
        response = self.client.post(
            '/api/v1/tracking/premium-features/purchase/',
            {'feature_id': str(self.feature.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        purchase_data = response.data
        self.assertIn('message', purchase_data)
        self.assertIn('purchase', purchase_data)
        print(f"✅ Purchased feature: {purchase_data['message']}")
        
        # Step 5: Check active premium features
        print("\n✨ Step 5: Check Active Features")
        response = self.client.get('/api/v1/tracking/user-premium-features/active/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        active_features = response.data
        self.assertEqual(len(active_features), 1)
        self.assertEqual(active_features[0]['feature_details']['name'], 'API Test Feature')
        print(f"✅ Active features: {len(active_features)}")
        
        # Step 6: Check updated balance
        print("\n💸 Step 6: Check Updated Balance")
        response = self.client.get('/api/v1/tracking/driver-currency/balance/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        new_balance = response.data['balance']
        self.assertEqual(new_balance, 2000 - 600)  # Original - cost
        print(f"✅ New balance after purchase: {new_balance} coins")
        
        # Step 7: Get transaction history
        print("\n📜 Step 7: Get Transaction History")
        response = self.client.get('/api/v1/tracking/driver-currency/transactions/?limit=10')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        transactions = response.data
        self.assertGreater(len(transactions), 0)
        # Check that the purchase transaction is recorded
        purchase_transaction = next(
            (t for t in transactions if t['transaction_type'] == 'premium_purchase'),
            None
        )
        self.assertIsNotNone(purchase_transaction)
        print(f"✅ Transaction history: {len(transactions)} transactions")
        
        # Step 8: Check feature access
        print("\n🔐 Step 8: Verify Feature Access")
        # Find the purchased feature
        purchased_feature = UserPremiumFeature.objects.get(
            user=self.driver_user,
            feature=self.feature
        )
        
        response = self.client.post(
            f'/api/v1/tracking/user-premium-features/{purchased_feature.id}/check_access/',
            {'feature_type': 'route_analytics'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        access_data = response.data
        self.assertTrue(access_data['has_access'])
        print(f"✅ Feature access confirmed: {access_data['has_access']}")
        
        # Step 9: Get earnings summary
        print("\n📈 Step 9: Get Earnings Summary")
        response = self.client.get('/api/v1/tracking/driver-currency/earnings_summary/?days=30')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        earnings = response.data
        self.assertIn('total_earned', earnings)
        self.assertIn('transaction_count', earnings)
        print(f"✅ Earnings summary: {earnings.get('total_earned', 0)} coins earned")
        
        # Step 10: Get performance leaderboard
        print("\n🏆 Step 10: Check Leaderboard Position")
        response = self.client.get('/api/v1/tracking/driver-performance/leaderboard/?limit=10')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        leaderboard = response.data
        self.assertIn('leaderboard', leaderboard)
        self.assertGreater(len(leaderboard['leaderboard']), 0)
        print(f"✅ Leaderboard position available")
        
        print("\n🎉 Complete API Integration Test Successful!")

    def test_unauthorized_access_protection(self):
        """Test that unauthorized users cannot access driver endpoints."""
        print("\n🔒 Testing Security & Access Control")
        
        # Test without authentication
        response = self.client.get('/api/v1/tracking/driver-performance/my_stats/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        print("✅ Unauthenticated access properly blocked")
        
        # Test with passenger user
        passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            user_type='passenger'
        )
        
        self.client.force_authenticate(user=passenger_user)
        response = self.client.get('/api/v1/tracking/driver-performance/my_stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        print("✅ Passenger access to driver endpoints properly blocked")
        
        print("\n🛡️ Security Test Successful!")


class StressTest(TestCase):
    """Stress test for high-volume operations."""

    def setUp(self):
        """Set up stress test data."""
        self.driver_user = User.objects.create_user(
            email='stress_driver@test.com',
            password='testpass123',
            user_type='driver'
        )
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000003',
            id_card_number='1234567892',
            driver_license_number='DL123458',
            years_of_experience=10,
            status='approved'
        )

    def test_high_volume_transactions(self):
        """Test system performance with high volume of transactions."""
        print("⚡ Stress Testing High-Volume Transactions")
        
        # Create 100 transactions rapidly
        for i in range(100):
            DriverCurrencyService.add_driver_currency(
                self.driver_user,
                10,
                'route_completion',
                f'Stress test transaction {i}'
            )
        
        # Verify all transactions were recorded
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        transactions = CurrencyTransaction.objects.filter(user=self.driver_user)
        
        self.assertEqual(currency.balance, 1100)  # 100 default + (100 * 10)
        self.assertEqual(transactions.count(), 100)
        self.assertEqual(currency.lifetime_earned, 1000)  # 100 * 10
        
        print(f"✅ Successfully processed {transactions.count()} transactions")
        print(f"✅ Final balance: {currency.balance} coins")
        print("⚡ Stress Test Completed Successfully!")