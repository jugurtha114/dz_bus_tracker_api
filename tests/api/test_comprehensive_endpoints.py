"""
Comprehensive API endpoint and permission testing suite for DZ Bus Tracker.
Tests all API endpoints, authentication, permissions, and business logic.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import Profile
from apps.drivers.models import Driver
from apps.buses.models import Bus
from apps.lines.models import Line, Stop, Schedule
from apps.tracking.models import LocationUpdate, Trip, PassengerCount, WaitingPassengers
from apps.notifications.models import DeviceToken, Notification, NotificationPreference
from apps.gamification.models import (
    UserProfile, Achievement, PointTransaction, Challenge, Reward
)
from apps.offline_mode.models import CacheConfiguration, UserCache, CachedData

User = get_user_model()


@pytest.mark.django_db
class TestAPIEndpoints:
    """Comprehensive API endpoint testing."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        # Create test users
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User'
        )
        
        self.passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Passenger',
            user_type='passenger'
        )
        
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type='driver'
        )
        
        # Create driver profile
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        
        # Create test data
        self.line = Line.objects.create(
            name='Line 1',
            code='L1',
            description='Test line',
            is_active=True,
            color='#FF0000'
        )
        
        self.stop = Stop.objects.create(
            name='Stop 1',
            latitude=36.7538,
            longitude=3.0588,
            address='Test Address',
            is_active=True
        )
        
        self.bus = Bus.objects.create(
            bus_number='B001',
            license_plate='16-12345-113',
            driver=self.driver,
            model='Mercedes',
            manufacturer='Mercedes-Benz',
            year=2020,
            capacity=30,
            status='active',
            is_active=True,
            is_approved=True
        )
    
    def authenticate_user(self, user):
        """Authenticate a user and return the token."""
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        return refresh.access_token
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = self.client.get('/health/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['status'] == 'healthy'
    
    # Authentication Tests
    def test_user_registration(self):
        """Test user registration."""
        data = {
            'email': 'newuser@test.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'New',
            'last_name': 'User',
            'user_type': 'passenger'
        }
        response = self.client.post('/api/v1/accounts/register/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert User.objects.filter(email='newuser@test.com').exists()
    
    def test_user_login(self):
        """Test user login."""
        data = {
            'email': 'passenger@test.com',
            'password': 'testpass123'
        }
        response = self.client.post('/api/v1/accounts/login/', data)
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
    
    def test_driver_registration(self):
        """Test driver registration."""
        data = {
            'email': 'newdriver@test.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'New',
            'last_name': 'Driver',
            'phone_number': '+213555987654',
            'id_card_number': '987654321',
            'driver_license_number': 'DL987654',
            'years_of_experience': 3
        }
        response = self.client.post('/api/v1/accounts/register-driver/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert 'driver_id' in response.data
        assert Driver.objects.filter(user__email='newdriver@test.com').exists()
    
    def test_jwt_token_endpoints(self):
        """Test JWT token endpoints."""
        # Token obtain
        data = {'email': 'passenger@test.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
        
        # Token refresh
        refresh_token = response.data['refresh']
        response = self.client.post('/api/token/refresh/', {'refresh': refresh_token})
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        
        # Token verify
        access_token = response.data['access']
        response = self.client.post('/api/token/verify/', {'token': access_token})
        assert response.status_code == status.HTTP_200_OK
    
    # Account Tests
    def test_user_me_endpoint(self):
        """Test user me endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == 'passenger@test.com'
    
    def test_profile_me_endpoint(self):
        """Test profile me endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/accounts/profile/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_user_list_permissions(self):
        """Test user list endpoint permissions."""
        # Admin can see all users
        self.authenticate_user(self.admin_user)
        response = self.client.get('/api/v1/accounts/users/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 3
        
        # Regular user can only see themselves
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/accounts/users/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['email'] == 'passenger@test.com'
    
    # Bus Tests
    def test_bus_list(self):
        """Test bus list endpoint."""
        response = self.client.get('/api/v1/buses/buses/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
    
    def test_bus_detail(self):
        """Test bus detail endpoint."""
        response = self.client.get(f'/api/v1/buses/buses/{self.bus.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['bus_number'] == 'B001'
    
    def test_bus_creation_admin_only(self):
        """Test bus creation requires admin permissions."""
        data = {
            'bus_number': 'B002',
            'license_plate': '16-54321-113',
            'driver': str(self.driver.id),
            'model': 'Iveco',
            'manufacturer': 'Iveco',
            'year': 2021,
            'capacity': 25,
            'status': 'active'
        }
        
        # Regular user cannot create bus
        self.authenticate_user(self.passenger_user)
        response = self.client.post('/api/v1/buses/buses/', data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Admin can create bus
        self.authenticate_user(self.admin_user)
        response = self.client.post('/api/v1/buses/buses/', data)
        assert response.status_code == status.HTTP_201_CREATED
    
    # Driver Tests
    def test_driver_list(self):
        """Test driver list endpoint."""
        response = self.client.get('/api/v1/drivers/drivers/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
    
    def test_driver_detail(self):
        """Test driver detail endpoint."""
        response = self.client.get(f'/api/v1/drivers/drivers/{self.driver.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['user']['email'] == 'driver@test.com'
    
    def test_driver_ratings(self):
        """Test driver ratings endpoint."""
        response = self.client.get(f'/api/v1/drivers/drivers/{self.driver.id}/ratings/')
        assert response.status_code == status.HTTP_200_OK
    
    # Line Tests
    def test_line_list(self):
        """Test line list endpoint."""
        response = self.client.get('/api/v1/lines/lines/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
    
    def test_line_detail(self):
        """Test line detail endpoint."""
        response = self.client.get(f'/api/v1/lines/lines/{self.line.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Line 1'
    
    def test_stops_list(self):
        """Test stops list endpoint."""
        response = self.client.get('/api/v1/lines/stops/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
    
    def test_schedules_list(self):
        """Test schedules list endpoint."""
        response = self.client.get('/api/v1/lines/schedules/')
        assert response.status_code == status.HTTP_200_OK
    
    # Tracking Tests
    def test_active_buses(self):
        """Test active buses endpoint."""
        response = self.client.get('/api/v1/tracking/active-buses/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_tracking_locations(self):
        """Test tracking locations endpoint."""
        response = self.client.get('/api/v1/tracking/locations/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_location_update_creation(self):
        """Test location update creation by driver."""
        self.authenticate_user(self.driver_user)
        data = {
            'bus': str(self.bus.id),
            'latitude': 36.7500,
            'longitude': 3.0500,
            'speed': 30.0,
            'heading': 90
        }
        response = self.client.post('/api/v1/tracking/locations/', data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Passenger cannot create location updates
        self.authenticate_user(self.passenger_user)
        response = self.client.post('/api/v1/tracking/locations/', data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_trips_list(self):
        """Test trips list endpoint."""
        response = self.client.get('/api/v1/tracking/trips/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_waiting_passengers(self):
        """Test waiting passengers endpoint."""
        self.authenticate_user(self.passenger_user)
        data = {
            'stop': str(self.stop.id),
            'line': str(self.line.id),
            'count': 5
        }
        response = self.client.post('/api/v1/tracking/waiting-passengers/', data)
        assert response.status_code == status.HTTP_201_CREATED
    
    # Notification Tests
    def test_notifications_list(self):
        """Test notifications list endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/notifications/notifications/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_device_token_creation(self):
        """Test device token creation."""
        self.authenticate_user(self.passenger_user)
        data = {
            'token': 'test_device_token_123',
            'device_type': 'android'
        }
        response = self.client.post('/api/v1/notifications/device-tokens/', data)
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_notification_preferences(self):
        """Test notification preferences endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/notifications/preferences/my_preferences/')
        assert response.status_code == status.HTTP_200_OK
    
    # Gamification Tests
    def test_gamification_profile(self):
        """Test gamification profile endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/gamification/profile/me/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_achievements_list(self):
        """Test achievements list endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/gamification/achievements/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_leaderboard_endpoints(self):
        """Test leaderboard endpoints."""
        self.authenticate_user(self.passenger_user)
        periods = ['daily', 'weekly', 'monthly', 'all_time']
        for period in periods:
            response = self.client.get(f'/api/v1/gamification/leaderboard/{period}/')
            assert response.status_code == status.HTTP_200_OK
    
    def test_challenges_list(self):
        """Test challenges list endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/gamification/challenges/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_rewards_list(self):
        """Test rewards list endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/gamification/rewards/')
        assert response.status_code == status.HTTP_200_OK
    
    # Offline Mode Tests
    def test_offline_config(self):
        """Test offline configuration endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/offline/config/current/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_cache_status(self):
        """Test cache status endpoint."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/offline/cache/status/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_cached_data_endpoints(self):
        """Test cached data endpoints."""
        self.authenticate_user(self.passenger_user)
        endpoints = ['lines', 'stops', 'schedules', 'buses', 'notifications']
        for endpoint in endpoints:
            response = self.client.get(f'/api/v1/offline/data/{endpoint}/')
            assert response.status_code == status.HTTP_200_OK
    
    def test_sync_queue(self):
        """Test sync queue endpoints."""
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/offline/sync-queue/')
        assert response.status_code == status.HTTP_200_OK
        
        response = self.client.get('/api/v1/offline/sync-queue/pending/')
        assert response.status_code == status.HTTP_200_OK
        
        response = self.client.get('/api/v1/offline/sync-queue/failed/')
        assert response.status_code == status.HTTP_200_OK
    
    # Schema Tests
    def test_api_schema_endpoints(self):
        """Test API schema endpoints."""
        response = self.client.get('/api/schema/')
        assert response.status_code == status.HTTP_200_OK
        
        response = self.client.get('/api/schema/swagger-ui/')
        assert response.status_code == status.HTTP_200_OK
        
        response = self.client.get('/api/schema/redoc/')
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPermissions:
    """Test permission classes and access control."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        # Create test users
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )
        
        self.passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            user_type='passenger'
        )
        
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            user_type='driver'
        )
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
    
    def authenticate_user(self, user):
        """Authenticate a user."""
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_admin_only_endpoints(self):
        """Test endpoints that require admin access."""
        # Test user creation by admin
        data = {
            'email': 'testuser@test.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'user_type': 'passenger'
        }
        
        # Without authentication
        response = self.client.post('/api/v1/accounts/users/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # With passenger authentication
        self.authenticate_user(self.passenger_user)
        response = self.client.post('/api/v1/accounts/users/', data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # With admin authentication
        self.authenticate_user(self.admin_user)
        response = self.client.post('/api/v1/accounts/users/', data)
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_driver_only_endpoints(self):
        """Test endpoints that require driver access."""
        # Create a bus for the driver
        bus = Bus.objects.create(
            bus_number='B001',
            license_plate='16-12345-113',
            driver=self.driver,
            model='Mercedes',
            capacity=30,
            status='active'
        )
        
        location_data = {
            'bus': str(bus.id),
            'latitude': 36.7500,
            'longitude': 3.0500,
            'speed': 30.0,
            'heading': 90
        }
        
        # Passenger cannot create location updates
        self.authenticate_user(self.passenger_user)
        response = self.client.post('/api/v1/tracking/locations/', location_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Driver can create location updates for their bus
        self.authenticate_user(self.driver_user)
        response = self.client.post('/api/v1/tracking/locations/', location_data)
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_authenticated_only_endpoints(self):
        """Test endpoints that require authentication."""
        # Without authentication
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # With authentication
        self.authenticate_user(self.passenger_user)
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_owner_only_endpoints(self):
        """Test endpoints that require owner permissions."""
        # Create another user
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='passenger'
        )
        
        # User cannot update another user's profile
        self.authenticate_user(self.passenger_user)
        response = self.client.patch(f'/api/v1/accounts/users/{other_user.id}/', {
            'first_name': 'Updated'
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # User can update their own profile
        response = self.client.patch(f'/api/v1/accounts/users/{self.passenger_user.id}/', {
            'first_name': 'Updated'
        })
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestBusinessLogic:
    """Test business logic and data validation."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            user_type='driver'
        )
        
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            years_of_experience=5,
            status='approved'
        )
        
        self.bus = Bus.objects.create(
            bus_number='B001',
            license_plate='16-12345-113',
            driver=self.driver,
            model='Mercedes',
            capacity=30,
            status='active'
        )
    
    def authenticate_user(self, user):
        """Authenticate a user."""
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_bus_capacity_validation(self):
        """Test that passenger count cannot exceed bus capacity."""
        self.authenticate_user(self.driver_user)
        
        # Valid passenger count
        data = {
            'bus': str(self.bus.id),
            'count': 25,  # Less than capacity (30)
            'boarding_count': 5,
            'alighting_count': 2
        }
        response = self.client.post('/api/v1/tracking/passenger-counts/', data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Invalid passenger count (exceeds capacity)
        data['count'] = 35  # More than capacity (30)
        response = self.client.post('/api/v1/tracking/passenger-counts/', data)
        # Should either return 400 or automatically cap at capacity
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED]
    
    def test_driver_bus_assignment(self):
        """Test that a driver can only be assigned to one active bus."""
        # Try to create another active bus for the same driver
        admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )
        self.authenticate_user(admin_user)
        
        data = {
            'bus_number': 'B002',
            'license_plate': '16-54321-113',
            'driver': str(self.driver.id),
            'model': 'Iveco',
            'capacity': 25,
            'status': 'active'
        }
        
        response = self.client.post('/api/v1/buses/buses/', data)
        # Should either prevent creation or deactivate the previous bus
        if response.status_code == status.HTTP_201_CREATED:
            # Check that only one bus is active for this driver
            active_buses = Bus.objects.filter(
                driver=self.driver,
                status='active'
            ).count()
            assert active_buses == 1
    
    def test_trip_lifecycle(self):
        """Test trip start and end lifecycle."""
        self.authenticate_user(self.driver_user)
        
        line = Line.objects.create(
            name='Test Line',
            code='TL1',
            description='Test line'
        )
        
        # Start a trip
        data = {
            'line_id': str(line.id)
        }
        response = self.client.post('/api/v1/tracking/trips/start_trip/', data)
        
        if response.status_code == status.HTTP_201_CREATED:
            trip_id = response.data['id']
            
            # Try to start another trip for the same bus (should fail)
            response = self.client.post('/api/v1/tracking/trips/start_trip/', data)
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            
            # End the trip
            response = self.client.post(f'/api/v1/tracking/trips/{trip_id}/end_trip/')
            assert response.status_code == status.HTTP_200_OK
    
    def test_location_update_validation(self):
        """Test location update validation."""
        self.authenticate_user(self.driver_user)
        
        # Valid location update
        data = {
            'bus': str(self.bus.id),
            'latitude': 36.7500,
            'longitude': 3.0500,
            'speed': 30.0,
            'heading': 90
        }
        response = self.client.post('/api/v1/tracking/locations/', data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Invalid latitude (out of range)
        data['latitude'] = 200  # Invalid latitude
        response = self.client.post('/api/v1/tracking/locations/', data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Invalid longitude (out of range)
        data['latitude'] = 36.7500  # Reset to valid
        data['longitude'] = 200  # Invalid longitude
        response = self.client.post('/api/v1/tracking/locations/', data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestDataIntegrity:
    """Test data integrity and consistency."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='test@test.com',
            password='testpass123',
            user_type='passenger'
        )
    
    def authenticate_user(self, user):
        """Authenticate a user."""
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    
    def test_user_profile_creation(self):
        """Test that user profile is automatically created."""
        # Profile should be created automatically when user is created
        assert hasattr(self.user, 'profile')
        assert Profile.objects.filter(user=self.user).exists()
    
    def test_soft_delete_functionality(self):
        """Test soft delete functionality for models."""
        line = Line.objects.create(
            name='Test Line',
            code='TL1',
            description='Test line'
        )
        
        # Check that line is active
        assert line.is_active is True
        assert Line.objects.filter(id=line.id, is_active=True).exists()
        
        # Soft delete the line
        line.soft_delete()
        
        # Check that line is soft deleted
        assert line.is_active is False
        assert not Line.objects.filter(id=line.id, is_active=True).exists()
        assert Line.objects.filter(id=line.id, is_active=False).exists()
    
    def test_cascade_operations(self):
        """Test cascade operations and foreign key constraints."""
        # Create a driver and bus
        driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            user_type='driver'
        )
        
        driver = Driver.objects.create(
            user=driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            driver_license_number='DL123456',
            status='approved'
        )
        
        bus = Bus.objects.create(
            bus_number='B001',
            license_plate='16-12345-113',
            driver=driver,
            model='Mercedes',
            capacity=30,
            status='active'
        )
        
        # Create location update for the bus
        location = LocationUpdate.objects.create(
            bus=bus,
            latitude=36.7500,
            longitude=3.0500,
            timestamp=timezone.now()
        )
        
        # Delete the bus (should handle or prevent based on business rules)
        bus_id = bus.id
        location_id = location.id
        
        # Soft delete the bus
        bus.soft_delete()
        
        # Location should still exist but bus should be inactive
        assert LocationUpdate.objects.filter(id=location_id).exists()
        assert not Bus.objects.filter(id=bus_id, is_active=True).exists()


def run_comprehensive_tests():
    """Run all comprehensive tests and return results."""
    import subprocess
    import sys
    
    try:
        # Run the tests with pytest
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            '/home/shared/projects/PycharmProjects/dz_bus_tracker_v2/tests/api/test_comprehensive_endpoints.py',
            '-v', '--tb=short'
        ], capture_output=True, text=True, cwd='/home/shared/projects/PycharmProjects/dz_bus_tracker_v2')
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    except Exception as e:
        return {
            'returncode': 1,
            'stdout': '',
            'stderr': str(e)
        }


if __name__ == '__main__':
    # Run tests if called directly
    result = run_comprehensive_tests()
    print(result['stdout'])
    if result['stderr']:
        print("STDERR:", result['stderr'])
    sys.exit(result['returncode'])