"""
Tests for driver currency and premium features system.
"""
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.drivers.models import Driver
from apps.tracking.models import (
    CurrencyTransaction,
    DriverPerformanceScore,
    PremiumFeature,
    Trip,
    UserPremiumFeature,
    VirtualCurrency,
)
from apps.tracking.services.driver_services import (
    DriverCurrencyService,
    DriverPerformanceService,
    PremiumFeatureService,
)

User = get_user_model()


class DriverCurrencyServiceTests(TestCase):
    """Test suite for DriverCurrencyService."""

    def setUp(self):
        """Set up test data."""
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type='driver'
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )

    def test_add_driver_currency(self):
        """Test adding currency to driver account."""
        # Test initial currency creation
        DriverCurrencyService.add_driver_currency(
            self.driver_user,
            100,
            'route_completion',
            'Test route completion'
        )
        
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        self.assertEqual(currency.balance, 200)  # 100 welcome + 100 added
        self.assertEqual(currency.lifetime_earned, 100)
        
        # Test adding more currency
        DriverCurrencyService.add_driver_currency(
            self.driver_user,
            50,
            'on_time_performance',
            'On-time bonus'
        )
        
        currency.refresh_from_db()
        self.assertEqual(currency.balance, 250)
        self.assertEqual(currency.lifetime_earned, 150)
        
        # Verify transactions were created
        transactions = CurrencyTransaction.objects.filter(user=self.driver_user)
        self.assertEqual(transactions.count(), 2)

    def test_spend_driver_currency(self):
        """Test spending currency from driver account."""
        # Add initial currency
        DriverCurrencyService.add_driver_currency(
            self.driver_user,
            500,
            'route_completion',
            'Test route completion'
        )
        
        # Test successful spending
        success = DriverCurrencyService.spend_driver_currency(
            self.driver_user,
            200,
            'premium_purchase',
            'Test premium feature'
        )
        
        self.assertTrue(success)
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        self.assertEqual(currency.balance, 400)  # 600 - 200
        self.assertEqual(currency.lifetime_spent, 200)
        
        # Test insufficient balance
        success = DriverCurrencyService.spend_driver_currency(
            self.driver_user,
            500,  # More than available
            'premium_purchase',
            'Test overspend'
        )
        
        self.assertFalse(success)
        currency.refresh_from_db()
        self.assertEqual(currency.balance, 400)  # Unchanged

    def test_earnings_summary(self):
        """Test earnings summary calculation."""
        # Add multiple transactions
        DriverCurrencyService.add_driver_currency(
            self.driver_user, 100, 'route_completion', 'Trip 1'
        )
        DriverCurrencyService.add_driver_currency(
            self.driver_user, 75, 'on_time_performance', 'Bonus 1'
        )
        DriverCurrencyService.add_driver_currency(
            self.driver_user, 50, 'safe_driving', 'Safety bonus'
        )
        
        summary = DriverCurrencyService.get_driver_earnings_summary(
            self.driver_user, 30
        )
        
        self.assertEqual(summary['total_earned'], 225)
        self.assertEqual(summary['transaction_count'], 3)
        self.assertEqual(summary['period_days'], 30)
        self.assertEqual(summary['average_per_day'], 225 / 30)


class DriverPerformanceServiceTests(TestCase):
    """Test suite for DriverPerformanceService."""

    def setUp(self):
        """Set up test data."""
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type='driver'
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )

    def test_get_or_create_performance_score(self):
        """Test performance score creation."""
        score = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        
        self.assertEqual(score.driver, self.driver)
        self.assertEqual(score.performance_level, 'rookie')
        self.assertEqual(score.total_trips, 0)
        self.assertEqual(score.safety_score, Decimal('100.00'))
        
        # Test getting existing score
        score2 = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        self.assertEqual(score.id, score2.id)

    def test_update_trip_performance(self):
        """Test trip performance updating."""
        score = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        
        # Test on-time trip
        DriverPerformanceService.update_trip_performance(
            self.driver, None, is_on_time=True
        )
        
        score.refresh_from_db()
        self.assertEqual(score.total_trips, 1)
        self.assertEqual(score.on_time_trips, 1)
        self.assertEqual(score.on_time_percentage, 100.0)
        
        # Test late trip
        DriverPerformanceService.update_trip_performance(
            self.driver, None, is_on_time=False
        )
        
        score.refresh_from_db()
        self.assertEqual(score.total_trips, 2)
        self.assertEqual(score.on_time_trips, 1)
        self.assertEqual(score.on_time_percentage, 50.0)
        
        # Verify currency was added
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        self.assertGreater(currency.balance, 100)  # More than welcome bonus

    def test_performance_level_progression(self):
        """Test performance level progression."""
        score = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        
        # Update to experienced level
        score.total_trips = 25
        score.on_time_trips = 20  # 80% on-time
        score.safety_score = Decimal('90.00')
        score.passenger_rating = Decimal('4.0')
        score.update_performance_level()
        
        self.assertEqual(score.performance_level, 'experienced')
        
        # Update to expert level
        score.total_trips = 60
        score.on_time_trips = 54  # 90% on-time
        score.safety_score = Decimal('95.00')
        score.passenger_rating = Decimal('4.5')
        score.update_performance_level()
        
        self.assertEqual(score.performance_level, 'expert')

    def test_coin_calculation(self):
        """Test coin calculation for trips."""
        score = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        
        # Test rookie level
        coins = DriverPerformanceService._calculate_trip_coins(score, True)
        self.assertEqual(coins, 75)  # 50 base + 25 on-time * 1.0 multiplier
        
        # Test with expert level
        score.performance_level = 'expert'
        coins = DriverPerformanceService._calculate_trip_coins(score, True)
        self.assertEqual(coins, 112)  # (50 + 25) * 1.5 multiplier
        
        # Test with streak bonus
        score.current_streak = 7
        coins = DriverPerformanceService._calculate_trip_coins(score, True)
        self.assertEqual(coins, 187)  # (50 + 25 + 50) * 1.5 multiplier

    def test_safety_score_update(self):
        """Test safety score updates."""
        score = DriverPerformanceService.get_or_create_performance_score(
            self.driver
        )
        
        # Test incident deduction
        DriverPerformanceService.update_safety_score(
            self.driver, 'accident', 'medium'
        )
        
        score.refresh_from_db()
        self.assertEqual(score.safety_score, Decimal('95.00'))  # 100 - 5
        
        # Test gradual improvement
        DriverPerformanceService.update_safety_score(self.driver)
        
        score.refresh_from_db()
        self.assertEqual(score.safety_score, Decimal('95.10'))


class PremiumFeatureServiceTests(TestCase):
    """Test suite for PremiumFeatureService."""

    def setUp(self):
        """Set up test data."""
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
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
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        
        # Create test features
        self.driver_feature = PremiumFeature.objects.create(
            name='Driver Analytics',
            feature_type='route_analytics',
            description='Analytics for drivers',
            cost_coins=500,
            duration_days=30,
            target_users='drivers',
            required_level='rookie'
        )
        
        self.passenger_feature = PremiumFeature.objects.create(
            name='Premium Notifications',
            feature_type='priority_support',
            description='Priority notifications',
            cost_coins=200,
            duration_days=30,
            target_users='passengers'
        )
        
        self.universal_feature = PremiumFeature.objects.create(
            name='Ad-Free',
            feature_type='custom_dashboard',
            description='No ads',
            cost_coins=300,
            duration_days=30,
            target_users='all'
        )

    def test_get_available_features_for_driver(self):
        """Test getting available features for driver."""
        features = PremiumFeatureService.get_available_features_for_user(
            self.driver_user
        )
        
        feature_names = [f.name for f in features]
        self.assertIn('Driver Analytics', feature_names)
        self.assertIn('Ad-Free', feature_names)
        self.assertNotIn('Premium Notifications', feature_names)

    def test_get_available_features_for_passenger(self):
        """Test getting available features for passenger."""
        features = PremiumFeatureService.get_available_features_for_user(
            self.passenger_user
        )
        
        feature_names = [f.name for f in features]
        self.assertIn('Premium Notifications', feature_names)
        self.assertIn('Ad-Free', feature_names)
        self.assertNotIn('Driver Analytics', feature_names)

    def test_purchase_feature_success(self):
        """Test successful feature purchase."""
        # Add sufficient currency
        VirtualCurrency.objects.create(
            user=self.driver_user,
            balance=1000
        )
        
        result = PremiumFeatureService.purchase_feature(
            self.driver_user,
            str(self.driver_feature.id)
        )
        
        self.assertTrue(result['success'])
        self.assertIn('purchase', result)
        
        # Verify purchase was created
        purchase = UserPremiumFeature.objects.get(
            user=self.driver_user,
            feature=self.driver_feature
        )
        self.assertTrue(purchase.is_active)
        self.assertEqual(purchase.coins_spent, 500)
        
        # Verify currency was deducted
        currency = VirtualCurrency.objects.get(user=self.driver_user)
        self.assertEqual(currency.balance, 500)

    def test_purchase_feature_insufficient_balance(self):
        """Test feature purchase with insufficient balance."""
        # Add insufficient currency
        VirtualCurrency.objects.create(
            user=self.driver_user,
            balance=100
        )
        
        result = PremiumFeatureService.purchase_feature(
            self.driver_user,
            str(self.driver_feature.id)
        )
        
        self.assertFalse(result['success'])
        self.assertIn('Insufficient balance', result['error'])

    def test_purchase_feature_already_owned(self):
        """Test purchasing already owned feature."""
        # Create existing purchase
        VirtualCurrency.objects.create(
            user=self.driver_user,
            balance=1000
        )
        
        UserPremiumFeature.objects.create(
            user=self.driver_user,
            feature=self.driver_feature,
            expires_at=timezone.now() + timedelta(days=15),
            coins_spent=500
        )
        
        result = PremiumFeatureService.purchase_feature(
            self.driver_user,
            str(self.driver_feature.id)
        )
        
        self.assertFalse(result['success'])
        self.assertIn('already owned', result['error'])

    def test_check_feature_access(self):
        """Test feature access checking."""
        # Create active purchase
        UserPremiumFeature.objects.create(
            user=self.driver_user,
            feature=self.driver_feature,
            expires_at=timezone.now() + timedelta(days=15),
            coins_spent=500,
            is_active=True
        )
        
        # Test access to purchased feature
        has_access = PremiumFeatureService.check_feature_access(
            self.driver_user,
            'route_analytics'
        )
        self.assertTrue(has_access)
        
        # Test access to non-purchased feature
        has_access = PremiumFeatureService.check_feature_access(
            self.driver_user,
            'priority_support'
        )
        self.assertFalse(has_access)

    def test_feature_expiration(self):
        """Test feature expiration handling."""
        # Create expired purchase
        expired_purchase = UserPremiumFeature.objects.create(
            user=self.driver_user,
            feature=self.driver_feature,
            expires_at=timezone.now() - timedelta(days=1),
            coins_spent=500,
            is_active=True
        )
        
        # Test expiration check
        self.assertTrue(expired_purchase.is_expired)
        
        # Test deactivation
        expired_purchase.deactivate_if_expired()
        expired_purchase.refresh_from_db()
        self.assertFalse(expired_purchase.is_active)


class DriverCurrencyAPITests(APITestCase):
    """Test suite for driver currency API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
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
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555000001',
            id_card_number='1234567890',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        
        # Create currency account
        VirtualCurrency.objects.create(
            user=self.driver_user,
            balance=1000,
            lifetime_earned=500
        )

    def test_driver_currency_balance_endpoint(self):
        """Test driver currency balance endpoint."""
        self.client.force_authenticate(user=self.driver_user)
        
        response = self.client.get('/api/v1/tracking/driver-currency/balance/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['balance'], 1000)
        self.assertEqual(response.data['lifetime_earned'], 500)

    def test_driver_currency_transactions_endpoint(self):
        """Test driver currency transactions endpoint."""
        # Create test transactions
        CurrencyTransaction.objects.create(
            user=self.driver_user,
            amount=100,
            transaction_type='route_completion',
            description='Test transaction',
            balance_after=1000
        )
        
        self.client.force_authenticate(user=self.driver_user)
        
        response = self.client.get('/api/v1/tracking/driver-currency/transactions/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['amount'], 100)

    def test_driver_performance_my_stats_endpoint(self):
        """Test driver performance my_stats endpoint."""
        # Create performance score
        DriverPerformanceScore.objects.create(
            driver=self.driver,
            total_trips=10,
            on_time_trips=8,
            performance_level='experienced'
        )
        
        self.client.force_authenticate(user=self.driver_user)
        
        response = self.client.get('/api/v1/tracking/driver-performance/my_stats/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('performance_score', response.data)
        self.assertIn('virtual_currency', response.data)
        self.assertEqual(
            response.data['performance_score']['performance_level'],
            'experienced'
        )

    def test_premium_features_available_endpoint(self):
        """Test premium features available endpoint."""
        # Create test feature
        PremiumFeature.objects.create(
            name='Test Feature',
            feature_type='route_analytics',
            description='Test description',
            cost_coins=500,
            duration_days=30,
            target_users='drivers'
        )
        
        self.client.force_authenticate(user=self.driver_user)
        
        response = self.client.get('/api/v1/tracking/premium-features/available/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Test Feature')

    def test_premium_feature_purchase_endpoint(self):
        """Test premium feature purchase endpoint."""
        # Create test feature
        feature = PremiumFeature.objects.create(
            name='Test Feature',
            feature_type='route_analytics',
            description='Test description',
            cost_coins=500,
            duration_days=30,
            target_users='drivers'
        )
        
        self.client.force_authenticate(user=self.driver_user)
        
        response = self.client.post(
            '/api/v1/tracking/premium-features/purchase/',
            {'feature_id': str(feature.id)}
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('message', response.data)
        self.assertIn('purchase', response.data)
        
        # Verify purchase was created
        purchase = UserPremiumFeature.objects.get(
            user=self.driver_user,
            feature=feature
        )
        self.assertTrue(purchase.is_active)

    def test_unauthorized_access(self):
        """Test unauthorized access to driver endpoints."""
        # Test without authentication
        response = self.client.get('/api/v1/tracking/driver-currency/balance/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Test passenger access to driver stats
        self.client.force_authenticate(user=self.passenger_user)
        response = self.client.get('/api/v1/tracking/driver-performance/my_stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ModelTests(TestCase):
    """Test suite for model functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@test.com',
            password='testpass123',
            user_type='driver'
        )

    def test_virtual_currency_model(self):
        """Test VirtualCurrency model functionality."""
        currency = VirtualCurrency.objects.create(
            user=self.user,
            balance=500
        )
        
        # Test string representation
        self.assertEqual(str(currency), f"{self.user.email} - 500 coins")
        
        # Test add_currency method
        currency.add_currency(100, "Test earning", "route_completion")
        self.assertEqual(currency.balance, 600)
        self.assertEqual(currency.lifetime_earned, 100)
        
        # Test spending
        currency.add_currency(-200, "Test spending", "premium_purchase")
        self.assertEqual(currency.balance, 400)
        self.assertEqual(currency.lifetime_spent, 200)

    def test_premium_feature_model(self):
        """Test PremiumFeature model functionality."""
        feature = PremiumFeature.objects.create(
            name='Test Feature',
            feature_type='route_analytics',
            description='Test description',
            cost_coins=500,
            duration_days=30,
            target_users='drivers'
        )
        
        self.assertEqual(str(feature), 'Test Feature - 500 coins')

    def test_user_premium_feature_expiration(self):
        """Test UserPremiumFeature expiration logic."""
        feature = PremiumFeature.objects.create(
            name='Test Feature',
            feature_type='route_analytics',
            description='Test description',
            cost_coins=500,
            duration_days=30,
            target_users='drivers'
        )
        
        # Test active feature
        purchase = UserPremiumFeature.objects.create(
            user=self.user,
            feature=feature,
            expires_at=timezone.now() + timedelta(days=10),
            coins_spent=500
        )
        
        self.assertFalse(purchase.is_expired)
        
        # Test expired feature
        purchase.expires_at = timezone.now() - timedelta(days=1)
        purchase.save()
        
        self.assertTrue(purchase.is_expired)
        
        # Test deactivation
        purchase.deactivate_if_expired()
        purchase.refresh_from_db()
        self.assertFalse(purchase.is_active)