"""
Tests for buses API endpoints.
"""
import tempfile
from decimal import Decimal
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.buses.models import Bus, BusLocation
from apps.drivers.models import Driver
from apps.core.constants import (
    USER_TYPE_DRIVER, USER_TYPE_PASSENGER, 
    BUS_STATUS_ACTIVE, BUS_STATUS_INACTIVE,
    DRIVER_STATUS_APPROVED
)


class BusesAPITestCase(APITestCase):
    """Base test case for buses API."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.passenger_user = User.objects.create_user(
            email='passenger@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Passenger',
            user_type=USER_TYPE_PASSENGER
        )
        
        self.driver_user = User.objects.create_user(
            email='driver@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            is_staff=True
        )
        
        # Profiles are created automatically via signals
        
        # Create driver profile
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            id_card_photo=self.create_test_image(),
            driver_license_number='DL123456',
            driver_license_photo=self.create_test_image(),
            status=DRIVER_STATUS_APPROVED,
            years_of_experience=5
        )
        
        # Create test bus
        self.bus = Bus.objects.create(
            license_plate='ABC123DZ',
            driver=self.driver,
            model='Mercedes Sprinter',
            manufacturer='Mercedes-Benz',
            year=2020,
            capacity=25,
            status=BUS_STATUS_ACTIVE,
            is_air_conditioned=True,
            description='Test bus description',
            is_approved=True
        )
        
        # Create bus location
        self.bus_location = BusLocation.objects.create(
            bus=self.bus,
            latitude=Decimal('36.7528'),
            longitude=Decimal('3.0424'),
            speed=Decimal('45.50'),
            heading=Decimal('180.0'),
            accuracy=Decimal('5.0'),
            passenger_count=15
        )
    
    def get_jwt_token(self, user):
        """Get JWT token for user."""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    
    def authenticate(self, user):
        """Authenticate user."""
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    
    def create_test_image(self):
        """Create a test image for upload."""
        image = Image.new('RGB', (100, 100), color='red')
        temp_file = BytesIO()
        image.save(temp_file, format='JPEG')
        temp_file.seek(0)
        return SimpleUploadedFile(
            'test_image.jpg',
            temp_file.getvalue(),
            content_type='image/jpeg'
        )


class BusViewSetTestCase(BusesAPITestCase):
    """Test cases for BusViewSet."""
    
    def test_list_buses_unauthenticated(self):
        """Test listing buses without authentication."""
        url = reverse('bus-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_buses_as_passenger(self):
        """Test listing buses as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('bus-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_list_buses_as_driver(self):
        """Test listing buses as driver."""
        self.authenticate(self.driver_user)
        url = reverse('bus-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_buses_as_admin(self):
        """Test listing buses as admin."""
        self.authenticate(self.admin_user)
        url = reverse('bus-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_bus_as_passenger(self):
        """Test retrieving bus as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['license_plate'], self.bus.license_plate)
    
    def test_retrieve_bus_as_driver_owner(self):
        """Test retrieving bus as driver owner."""
        self.authenticate(self.driver_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_create_bus_as_driver(self):
        """Test creating bus as driver."""
        self.authenticate(self.driver_user)
        url = reverse('bus-list')
        data = {
            'license_plate': 'XYZ789DZ',
            'model': 'Iveco Daily',
            'manufacturer': 'Iveco',
            'year': 2021,
            'capacity': 30,
            'is_air_conditioned': False,
            'description': 'New bus'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Bus.objects.filter(license_plate='XYZ789DZ').exists())
        
        # Check that driver is automatically assigned
        new_bus = Bus.objects.get(license_plate='XYZ789DZ')
        self.assertEqual(new_bus.driver, self.driver)
    
    def test_create_bus_as_passenger(self):
        """Test creating bus as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('bus-list')
        data = {
            'license_plate': 'XYZ789DZ',
            'model': 'Iveco Daily',
            'manufacturer': 'Iveco',
            'year': 2021,
            'capacity': 30
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_bus_invalid_data(self):
        """Test creating bus with invalid data."""
        self.authenticate(self.driver_user)
        url = reverse('bus-list')
        data = {
            'license_plate': '',  # Invalid: empty
            'model': 'Test Model',
            'year': 1999,  # Could be invalid depending on validation
            'capacity': -5  # Invalid: negative
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_bus_as_owner(self):
        """Test updating bus as owner driver."""
        self.authenticate(self.driver_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        data = {
            'model': 'Updated Model',
            'capacity': 30,
            'description': 'Updated description'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bus.refresh_from_db()
        self.assertEqual(self.bus.model, 'Updated Model')
        self.assertEqual(self.bus.capacity, 30)
    
    def test_update_bus_as_passenger(self):
        """Test updating bus as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        data = {'model': 'Hacked Model'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_bus_photo(self):
        """Test updating bus photo."""
        self.authenticate(self.driver_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        test_image = self.create_test_image()
        data = {'photo': test_image}
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bus.refresh_from_db()
        self.assertTrue(self.bus.photo)
    
    def test_delete_bus_as_owner(self):
        """Test deleting bus as owner driver."""
        self.authenticate(self.driver_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.bus.refresh_from_db()
        self.assertFalse(self.bus.is_active)
    
    def test_delete_bus_as_admin(self):
        """Test deleting bus as admin."""
        self.authenticate(self.admin_user)
        url = reverse('bus-detail', kwargs={'pk': self.bus.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_filter_buses_by_status(self):
        """Test filtering buses by status."""
        # Create inactive bus
        inactive_bus = Bus.objects.create(
            license_plate='INACTIVE123',
            driver=self.driver,
            model='Old Bus',
            manufacturer='Old Manufacturer',
            year=2015,
            capacity=20,
            status=BUS_STATUS_INACTIVE
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('bus-list')
        
        # Filter active buses
        response = self.client.get(url, {'status': BUS_STATUS_ACTIVE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_count = len(response.data['results'])
        
        # Filter inactive buses
        response = self.client.get(url, {'status': BUS_STATUS_INACTIVE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inactive_count = len(response.data['results'])
        
        self.assertGreaterEqual(active_count, 1)
        self.assertGreaterEqual(inactive_count, 1)
    
    def test_search_buses(self):
        """Test searching buses."""
        self.authenticate(self.passenger_user)
        url = reverse('bus-list')
        
        # Search by license plate
        response = self.client.get(url, {'search': 'ABC123'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
        
        # Search by model
        response = self.client.get(url, {'search': 'Mercedes'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)


class BusLocationViewSetTestCase(BusesAPITestCase):
    """Test cases for BusLocationViewSet."""
    
    def test_list_bus_locations_unauthenticated(self):
        """Test listing bus locations without authentication."""
        url = reverse('buslocation-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_bus_locations_as_passenger(self):
        """Test listing bus locations as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('buslocation-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_retrieve_bus_location(self):
        """Test retrieving bus location."""
        self.authenticate(self.passenger_user)
        url = reverse('buslocation-detail', kwargs={'pk': self.bus_location.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['latitude']), float(self.bus_location.latitude))
    
    def test_create_bus_location_as_driver(self):
        """Test creating bus location as driver."""
        self.authenticate(self.driver_user)
        url = reverse('buslocation-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '36.7500',
            'longitude': '3.0400',
            'speed': '50.0',
            'heading': '90.0',
            'accuracy': '3.0',
            'passenger_count': 20
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BusLocation.objects.filter(
            bus=self.bus,
            latitude=Decimal('36.7500')
        ).exists())
    
    def test_create_bus_location_as_passenger(self):
        """Test creating bus location as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('buslocation-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '36.7500',
            'longitude': '3.0400'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_bus_location_invalid_coordinates(self):
        """Test creating bus location with invalid coordinates."""
        self.authenticate(self.driver_user)
        url = reverse('buslocation-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '91.0000',  # Invalid: > 90
            'longitude': '181.0000'  # Invalid: > 180
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_bus_location_as_driver(self):
        """Test updating bus location as driver."""
        self.authenticate(self.driver_user)
        url = reverse('buslocation-detail', kwargs={'pk': self.bus_location.pk})
        data = {
            'passenger_count': 18,
            'is_tracking_active': False
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bus_location.refresh_from_db()
        self.assertEqual(self.bus_location.passenger_count, 18)
        self.assertFalse(self.bus_location.is_tracking_active)
    
    def test_delete_bus_location_as_admin(self):
        """Test deleting bus location as admin."""
        self.authenticate(self.admin_user)
        url = reverse('buslocation-detail', kwargs={'pk': self.bus_location.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_filter_bus_locations_by_bus(self):
        """Test filtering bus locations by bus."""
        self.authenticate(self.passenger_user)
        url = reverse('buslocation-list')
        response = self.client.get(url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for location in response.data['results']:
            self.assertEqual(location['bus'], str(self.bus.pk))
    
    def test_filter_bus_locations_by_tracking_status(self):
        """Test filtering bus locations by tracking status."""
        # Create inactive location
        BusLocation.objects.create(
            bus=self.bus,
            latitude=Decimal('36.7000'),
            longitude=Decimal('3.0000'),
            is_tracking_active=False
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('buslocation-list')
        
        # Filter active tracking
        response = self.client.get(url, {'is_tracking_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for location in response.data['results']:
            self.assertTrue(location['is_tracking_active'])
        
        # Filter inactive tracking
        response = self.client.get(url, {'is_tracking_active': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for location in response.data['results']:
            self.assertFalse(location['is_tracking_active'])


class BusesAPIIntegrationTestCase(BusesAPITestCase):
    """Integration tests for buses API."""
    
    def test_bus_lifecycle_flow(self):
        """Test complete bus lifecycle flow."""
        self.authenticate(self.driver_user)
        
        # Create new bus
        url = reverse('bus-list')
        bus_data = {
            'license_plate': 'NEW123DZ',
            'model': 'New Bus Model',
            'manufacturer': 'New Manufacturer',
            'year': 2022,
            'capacity': 35,
            'is_air_conditioned': True,
            'description': 'Brand new bus'
        }
        response = self.client.post(url, bus_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_bus_id = response.data['id']
        
        # Update bus details
        bus_url = reverse('bus-detail', kwargs={'pk': new_bus_id})
        update_data = {
            'description': 'Updated description',
            'features': ['wifi', 'usb_charging']
        }
        response = self.client.patch(bus_url, update_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Add bus location
        location_url = reverse('buslocation-list')
        location_data = {
            'bus': new_bus_id,
            'latitude': '36.7600',
            'longitude': '3.0500',
            'speed': '40.0',
            'passenger_count': 12
        }
        response = self.client.post(location_url, location_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify bus is visible to passengers
        self.authenticate(self.passenger_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bus_plates = [bus['license_plate'] for bus in response.data['results']]
        self.assertIn('NEW123DZ', bus_plates)
    
    def test_real_time_tracking_flow(self):
        """Test real-time tracking flow."""
        self.authenticate(self.driver_user)
        
        # Start tracking - create multiple locations
        location_url = reverse('buslocation-list')
        locations = [
            {'latitude': '36.7500', 'longitude': '3.0400', 'passenger_count': 10},
            {'latitude': '36.7510', 'longitude': '3.0410', 'passenger_count': 12},
            {'latitude': '36.7520', 'longitude': '3.0420', 'passenger_count': 15},
        ]
        
        for i, loc_data in enumerate(locations):
            loc_data['bus'] = self.bus.pk
            loc_data['speed'] = str(30 + i * 5)  # Varying speed
            response = self.client.post(location_url, loc_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Passenger checks bus locations
        self.authenticate(self.passenger_user)
        response = self.client.get(location_url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
        
        # Check locations are ordered by creation time (most recent first)
        locations_response = response.data['results']
        self.assertTrue(
            locations_response[0]['created_at'] >= locations_response[1]['created_at']
        )
    
    def test_bus_permissions_across_users(self):
        """Test bus permissions across different user types."""
        # Admin can see all buses and locations
        self.authenticate(self.admin_user)
        bus_url = reverse('bus-list')
        response = self.client.get(bus_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        location_url = reverse('buslocation-list')
        response = self.client.get(location_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Passenger can see buses and locations but cannot modify
        self.authenticate(self.passenger_user)
        response = self.client.get(bus_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response = self.client.get(location_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Passenger cannot create/update buses
        bus_data = {'license_plate': 'HACK123', 'model': 'Hack'}
        response = self.client.post(bus_url, bus_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Driver can manage their own buses
        self.authenticate(self.driver_user)
        response = self.client.patch(
            reverse('bus-detail', kwargs={'pk': self.bus.pk}),
            {'description': 'Updated by owner'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)