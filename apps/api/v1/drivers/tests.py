"""
Tests for drivers API endpoints.
"""
import tempfile
from datetime import date
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
from apps.drivers.models import Driver, DriverRating
from apps.core.constants import (
    USER_TYPE_DRIVER, USER_TYPE_PASSENGER, 
    DRIVER_STATUS_PENDING, DRIVER_STATUS_APPROVED, DRIVER_STATUS_REJECTED
)


class DriversAPITestCase(APITestCase):
    """Base test case for drivers API."""
    
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
        
        self.driver_user2 = User.objects.create_user(
            email='driver2@test.com',
            password='testpass123',
            first_name='Another',
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
        
        # Create driver profiles
        self.driver = Driver.objects.create(
            user=self.driver_user,
            phone_number='+213555123456',
            id_card_number='123456789',
            id_card_photo=self.create_test_image(),
            driver_license_number='DL123456',
            driver_license_photo=self.create_test_image(),
            status=DRIVER_STATUS_APPROVED,
            years_of_experience=5,
            rating=Decimal('4.5'),
            total_ratings=10
        )
        
        self.driver2 = Driver.objects.create(
            user=self.driver_user2,
            phone_number='+213555654321',
            id_card_number='987654321',
            id_card_photo=self.create_test_image(),
            driver_license_number='DL654321',
            driver_license_photo=self.create_test_image(),
            status=DRIVER_STATUS_PENDING,
            years_of_experience=2
        )
        
        # Create driver rating
        self.rating = DriverRating.objects.create(
            driver=self.driver,
            user=self.passenger_user,
            rating=5,
            comment='Excellent driver!',
            rating_date=date.today()
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


class DriverViewSetTestCase(DriversAPITestCase):
    """Test cases for DriverViewSet."""
    
    def test_list_drivers_unauthenticated(self):
        """Test listing drivers without authentication."""
        url = reverse('driver-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_drivers_as_passenger(self):
        """Test listing drivers as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_list_drivers_as_driver(self):
        """Test listing drivers as driver."""
        self.authenticate(self.driver_user)
        url = reverse('driver-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_drivers_as_admin(self):
        """Test listing drivers as admin."""
        self.authenticate(self.admin_user)
        url = reverse('driver-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 2)
    
    def test_retrieve_driver_as_passenger(self):
        """Test retrieving driver as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id_card_number'], self.driver.id_card_number)
    
    def test_retrieve_driver_as_owner(self):
        """Test retrieving driver as owner."""
        self.authenticate(self.driver_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_create_driver_as_user_without_driver_profile(self):
        """Test creating driver profile for user."""
        # Create new driver user
        new_driver_user = User.objects.create_user(
            email='newdriver@test.com',
            password='testpass123',
            first_name='New',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        # Profile created automatically via signals
        
        self.authenticate(new_driver_user)
        url = reverse('driver-list')
        data = {
            'phone_number': '+213555999888',
            'id_card_number': '111222333',
            'id_card_photo': self.create_test_image(),
            'driver_license_number': 'DL999888',
            'driver_license_photo': self.create_test_image(),
            'years_of_experience': 3
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Driver.objects.filter(user=new_driver_user).exists())
        
        # Check default status is pending
        new_driver = Driver.objects.get(user=new_driver_user)
        self.assertEqual(new_driver.status, DRIVER_STATUS_PENDING)
    
    def test_create_driver_as_passenger_user(self):
        """Test creating driver profile as passenger user."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-list')
        data = {
            'phone_number': '+213555999888',
            'id_card_number': '111222333',
            'years_of_experience': 3
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_driver_duplicate_id_card(self):
        """Test creating driver with duplicate ID card number."""
        new_driver_user = User.objects.create_user(
            email='newdriver@test.com',
            password='testpass123',
            user_type=USER_TYPE_DRIVER
        )
        self.authenticate(new_driver_user)
        url = reverse('driver-list')
        data = {
            'phone_number': '+213555999888',
            'id_card_number': '123456789',  # Same as existing driver
            'driver_license_number': 'DL999888',
            'years_of_experience': 3
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_driver_as_owner(self):
        """Test updating driver as owner."""
        self.authenticate(self.driver_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        data = {
            'phone_number': '+213555111222',
            'years_of_experience': 7,
            'is_available': False
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.phone_number, '+213555111222')
        self.assertEqual(self.driver.years_of_experience, 7)
        self.assertFalse(self.driver.is_available)
    
    def test_update_driver_as_other_driver(self):
        """Test updating driver as different driver."""
        self.authenticate(self.driver_user2)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        data = {'years_of_experience': 10}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_driver_photos(self):
        """Test updating driver photos."""
        self.authenticate(self.driver_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        
        new_id_photo = self.create_test_image()
        new_license_photo = self.create_test_image()
        data = {
            'id_card_photo': new_id_photo,
            'driver_license_photo': new_license_photo
        }
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertTrue(self.driver.id_card_photo)
        self.assertTrue(self.driver.driver_license_photo)
    
    def test_delete_driver_as_owner(self):
        """Test deleting driver as owner."""
        self.authenticate(self.driver_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.driver.refresh_from_db()
        self.assertFalse(self.driver.is_active)
    
    def test_delete_driver_as_admin(self):
        """Test deleting driver as admin."""
        self.authenticate(self.admin_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_filter_drivers_by_status(self):
        """Test filtering drivers by status."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-list')
        
        # Filter approved drivers
        response = self.client.get(url, {'status': DRIVER_STATUS_APPROVED})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for driver in response.data['results']:
            self.assertEqual(driver['status'], DRIVER_STATUS_APPROVED)
        
        # Filter pending drivers
        response = self.client.get(url, {'status': DRIVER_STATUS_PENDING})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for driver in response.data['results']:
            self.assertEqual(driver['status'], DRIVER_STATUS_PENDING)
    
    def test_filter_drivers_by_availability(self):
        """Test filtering drivers by availability."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-list')
        
        # Filter available drivers
        response = self.client.get(url, {'is_available': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for driver in response.data['results']:
            self.assertTrue(driver['is_available'])
    
    def test_search_drivers(self):
        """Test searching drivers."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-list')
        
        # Search by name
        response = self.client.get(url, {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
        
        # Search by ID card number
        response = self.client.get(url, {'search': '123456'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_approve_driver_as_admin(self):
        """Test approving driver as admin."""
        self.authenticate(self.admin_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver2.pk})
        data = {'status': DRIVER_STATUS_APPROVED}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver2.refresh_from_db()
        self.assertEqual(self.driver2.status, DRIVER_STATUS_APPROVED)
    
    def test_reject_driver_as_admin(self):
        """Test rejecting driver as admin."""
        self.authenticate(self.admin_user)
        url = reverse('driver-detail', kwargs={'pk': self.driver2.pk})
        data = {
            'status': DRIVER_STATUS_REJECTED,
            'rejection_reason': 'Invalid documents'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver2.refresh_from_db()
        self.assertEqual(self.driver2.status, DRIVER_STATUS_REJECTED)
        self.assertEqual(self.driver2.rejection_reason, 'Invalid documents')


class DriverRatingViewSetTestCase(DriversAPITestCase):
    """Test cases for DriverRatingViewSet."""
    
    def test_list_driver_ratings_unauthenticated(self):
        """Test listing driver ratings without authentication."""
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_driver_ratings_as_passenger(self):
        """Test listing driver ratings as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_retrieve_driver_rating(self):
        """Test retrieving driver rating."""
        self.authenticate(self.passenger_user)
        url = reverse(
            'driver-ratings-detail', 
            kwargs={'driver_pk': self.driver.pk, 'pk': self.rating.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rating'], self.rating.rating)
    
    def test_create_driver_rating_as_passenger(self):
        """Test creating driver rating as passenger."""
        # Create another passenger to rate
        another_passenger = User.objects.create_user(
            email='passenger2@test.com',
            password='testpass123',
            user_type=USER_TYPE_PASSENGER
        )
        Profile.objects.create(user=another_passenger)
        
        self.authenticate(another_passenger)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        data = {
            'rating': 4,
            'comment': 'Good driver'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DriverRating.objects.filter(
            driver=self.driver,
            user=another_passenger,
            rating=4
        ).exists())
    
    def test_create_driver_rating_as_driver(self):
        """Test creating driver rating as driver."""
        self.authenticate(self.driver_user)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        data = {
            'rating': 5,
            'comment': 'Self rating'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_duplicate_rating_same_day(self):
        """Test creating duplicate rating on same day."""
        self.authenticate(self.passenger_user)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        data = {
            'rating': 3,
            'comment': 'Another rating'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_rating_invalid_score(self):
        """Test creating rating with invalid score."""
        another_passenger = User.objects.create_user(
            email='passenger2@test.com',
            password='testpass123',
            user_type=USER_TYPE_PASSENGER
        )
        self.authenticate(another_passenger)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        
        # Test rating < 1
        data = {'rating': 0, 'comment': 'Invalid rating'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test rating > 5
        data = {'rating': 6, 'comment': 'Invalid rating'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_driver_rating_as_owner(self):
        """Test updating driver rating as owner."""
        self.authenticate(self.passenger_user)
        url = reverse(
            'driver-ratings-detail',
            kwargs={'driver_pk': self.driver.pk, 'pk': self.rating.pk}
        )
        data = {
            'rating': 4,
            'comment': 'Updated comment'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.rating, 4)
        self.assertEqual(self.rating.comment, 'Updated comment')
    
    def test_update_driver_rating_as_other_user(self):
        """Test updating driver rating as different user."""
        self.authenticate(self.driver_user2)
        url = reverse(
            'driver-ratings-detail',
            kwargs={'driver_pk': self.driver.pk, 'pk': self.rating.pk}
        )
        data = {'rating': 1}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_driver_rating_as_owner(self):
        """Test deleting driver rating as owner."""
        self.authenticate(self.passenger_user)
        url = reverse(
            'driver-ratings-detail',
            kwargs={'driver_pk': self.driver.pk, 'pk': self.rating.pk}
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DriverRating.objects.filter(pk=self.rating.pk).exists())
    
    def test_delete_driver_rating_as_admin(self):
        """Test deleting driver rating as admin."""
        self.authenticate(self.admin_user)
        url = reverse(
            'driver-ratings-detail',
            kwargs={'driver_pk': self.driver.pk, 'pk': self.rating.pk}
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class DriversAPIIntegrationTestCase(DriversAPITestCase):
    """Integration tests for drivers API."""
    
    def test_driver_registration_approval_flow(self):
        """Test complete driver registration and approval flow."""
        # Create new driver user
        new_driver_user = User.objects.create_user(
            email='newdriver@test.com',
            password='testpass123',
            first_name='New',
            last_name='Driver',
            user_type=USER_TYPE_DRIVER
        )
        # Profile created automatically via signals
        
        # Driver registers profile
        self.authenticate(new_driver_user)
        url = reverse('driver-list')
        data = {
            'phone_number': '+213555999888',
            'id_card_number': '111222333',
            'id_card_photo': self.create_test_image(),
            'driver_license_number': 'DL999888',
            'driver_license_photo': self.create_test_image(),
            'years_of_experience': 3
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_driver_id = response.data['id']
        
        # Check status is pending
        new_driver = Driver.objects.get(pk=new_driver_id)
        self.assertEqual(new_driver.status, DRIVER_STATUS_PENDING)
        
        # Admin approves driver
        self.authenticate(self.admin_user)
        driver_url = reverse('driver-detail', kwargs={'pk': new_driver_id})
        approval_data = {'status': DRIVER_STATUS_APPROVED}
        response = self.client.patch(driver_url, approval_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify driver is approved
        new_driver.refresh_from_db()
        self.assertEqual(new_driver.status, DRIVER_STATUS_APPROVED)
        
        # Driver appears in approved drivers list
        self.authenticate(self.passenger_user)
        drivers_url = reverse('driver-list')
        response = self.client.get(drivers_url, {'status': DRIVER_STATUS_APPROVED})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver_ids = [d['id'] for d in response.data['results']]
        self.assertIn(new_driver_id, driver_ids)
    
    def test_rating_system_flow(self):
        """Test driver rating system flow."""
        # Create multiple passengers
        passengers = []
        for i in range(3):
            passenger = User.objects.create_user(
                email=f'passenger{i}@test.com',
                password='testpass123',
                user_type=USER_TYPE_PASSENGER
            )
            # Profile created automatically via signals
            passengers.append(passenger)
        
        # Each passenger rates the driver
        ratings_data = [
            {'rating': 5, 'comment': 'Excellent!'},
            {'rating': 4, 'comment': 'Good driver'},
            {'rating': 5, 'comment': 'Very professional'}
        ]
        
        for passenger, rating_data in zip(passengers, ratings_data):
            self.authenticate(passenger)
            url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
            response = self.client.post(url, rating_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check driver ratings list
        self.authenticate(self.passenger_user)
        url = reverse('driver-ratings-list', kwargs={'driver_pk': self.driver.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 4)  # 3 new + 1 existing
        
        # Verify driver's average rating is updated
        self.driver.refresh_from_db()
        self.assertGreater(self.driver.total_ratings, 10)  # Was 10, now more
    
    def test_driver_permissions_flow(self):
        """Test driver permissions across different actions."""
        # Pending driver has limited access
        self.authenticate(self.driver_user2)
        
        # Can view their own profile
        url = reverse('driver-detail', kwargs={'pk': self.driver2.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Can update their own profile
        data = {'years_of_experience': 3}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Cannot update other drivers
        other_url = reverse('driver-detail', kwargs={'pk': self.driver.pk})
        response = self.client.patch(other_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Cannot approve/reject themselves
        data = {'status': DRIVER_STATUS_APPROVED}
        response = self.client.patch(url, data)
        # Status should remain unchanged (depends on serializer implementation)
        self.driver2.refresh_from_db()
        self.assertEqual(self.driver2.status, DRIVER_STATUS_PENDING)
        
        # Admin can approve
        self.authenticate(self.admin_user)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver2.refresh_from_db()
        self.assertEqual(self.driver2.status, DRIVER_STATUS_APPROVED)