"""
Tests for accounts API endpoints.
"""
import tempfile
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.core.constants import USER_TYPE_DRIVER, USER_TYPE_PASSENGER


class AccountsAPITestCase(APITestCase):
    """Base test case for accounts API."""
    
    def setUp(self):
        """Set up test data."""
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


class UserViewSetTestCase(AccountsAPITestCase):
    """Test cases for UserViewSet."""
    
    def test_list_users_unauthenticated(self):
        """Test listing users without authentication."""
        url = reverse('user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_users_as_passenger(self):
        """Test listing users as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('user-list')
        response = self.client.get(url)
        # Passenger can see users but only their own
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_list_users_as_admin(self):
        """Test listing users as admin."""
        self.authenticate(self.admin_user)
        url = reverse('user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    def test_retrieve_user_as_owner(self):
        """Test retrieving user as owner."""
        self.authenticate(self.passenger_user)
        url = reverse('user-detail', kwargs={'pk': self.passenger_user.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.passenger_user.email)
    
    def test_retrieve_user_as_other_user(self):
        """Test retrieving user as different user."""
        self.authenticate(self.passenger_user)
        url = reverse('user-detail', kwargs={'pk': self.driver_user.pk})
        response = self.client.get(url)
        # Should return 404 because the user is filtered out of the queryset
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_retrieve_user_as_admin(self):
        """Test retrieving user as admin."""
        self.authenticate(self.admin_user)
        url = reverse('user-detail', kwargs={'pk': self.passenger_user.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_create_user_unauthenticated(self):
        """Test creating user without authentication."""
        url = reverse('user-list')
        data = {
            'email': 'newuser@test.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'first_name': 'New',
            'last_name': 'User',
            'user_type': USER_TYPE_PASSENGER
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='newuser@test.com').exists())
    
    def test_create_user_invalid_data(self):
        """Test creating user with invalid data."""
        url = reverse('user-list')
        data = {
            'email': 'invalid-email',
            'password': 'short',
            'confirm_password': 'different',
            'user_type': USER_TYPE_PASSENGER
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_user_as_owner(self):
        """Test updating user as owner."""
        self.authenticate(self.passenger_user)
        url = reverse('user-detail', kwargs={'pk': self.passenger_user.pk})
        data = {
            'first_name': 'Updated',
            'last_name': 'Name'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.passenger_user.refresh_from_db()
        self.assertEqual(self.passenger_user.first_name, 'Updated')
    
    def test_update_user_as_other_user(self):
        """Test updating user as different user."""
        self.authenticate(self.passenger_user)
        url = reverse('user-detail', kwargs={'pk': self.driver_user.pk})
        data = {'first_name': 'Hacked'}
        response = self.client.patch(url, data)
        # Should return 404 because the user is filtered out of the queryset
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_delete_user_as_owner(self):
        """Test deleting user as owner."""
        self.authenticate(self.passenger_user)
        url = reverse('user-detail', kwargs={'pk': self.passenger_user.pk})
        response = self.client.delete(url)
        # Regular users cannot delete themselves, only admins can
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_user_as_admin(self):
        """Test deleting user as admin."""
        self.authenticate(self.admin_user)
        url = reverse('user-detail', kwargs={'pk': self.passenger_user.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class ProfileViewSetTestCase(AccountsAPITestCase):
    """Test cases for ProfileViewSet."""
    
    def test_list_profiles_unauthenticated(self):
        """Test listing profiles without authentication."""
        url = reverse('profile-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_profiles_as_passenger(self):
        """Test listing profiles as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('profile-list')
        response = self.client.get(url)
        # Passenger should only see their own profile
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_list_profiles_as_admin(self):
        """Test listing profiles as admin."""
        self.authenticate(self.admin_user)
        url = reverse('profile-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_profile_as_owner(self):
        """Test retrieving profile as owner."""
        self.authenticate(self.passenger_user)
        profile = self.passenger_user.profile
        url = reverse('profile-detail', kwargs={'pk': profile.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_profile_as_other_user(self):
        """Test retrieving profile as different user."""
        self.authenticate(self.passenger_user)
        profile = self.driver_user.profile
        url = reverse('profile-detail', kwargs={'pk': profile.pk})
        response = self.client.get(url)
        # Should return 404 because the profile is filtered out of the queryset
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_update_profile_as_owner(self):
        """Test updating profile as owner."""
        self.authenticate(self.passenger_user)
        profile = self.passenger_user.profile
        url = reverse('profile-detail', kwargs={'pk': profile.pk})
        data = {
            'bio': 'Updated bio',
            'language': 'ar',
            'push_notifications_enabled': False
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.bio, 'Updated bio')
        self.assertEqual(profile.language, 'ar')
        self.assertFalse(profile.push_notifications_enabled)
    
    def test_update_profile_avatar(self):
        """Test updating profile avatar."""
        self.authenticate(self.passenger_user)
        profile = self.passenger_user.profile
        url = reverse('profile-detail', kwargs={'pk': profile.pk})
        
        test_image = self.create_test_image()
        data = {'avatar': test_image}
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertTrue(profile.avatar)
    
    def test_create_profile_not_allowed(self):
        """Test creating profile is not allowed."""
        self.authenticate(self.passenger_user)
        url = reverse('profile-list')
        data = {'bio': 'Test bio'}
        response = self.client.post(url, data)
        # The view should not allow POST method
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_profile_not_allowed(self):
        """Test deleting profile is not allowed."""
        self.authenticate(self.passenger_user)
        profile = self.passenger_user.profile
        url = reverse('profile-detail', kwargs={'pk': profile.pk})
        response = self.client.delete(url)
        # The view should not allow DELETE method  
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AccountsAPIIntegrationTestCase(AccountsAPITestCase):
    """Integration tests for accounts API."""
    
    def test_user_registration_flow(self):
        """Test complete user registration flow."""
        # Register new user
        url = reverse('user-list')
        data = {
            'email': 'newuser@test.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
            'first_name': 'New',
            'last_name': 'User',
            'user_type': USER_TYPE_PASSENGER
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check user was created
        user = User.objects.get(email='newuser@test.com')
        self.assertTrue(user.check_password('testpass123'))
        self.assertEqual(user.user_type, USER_TYPE_PASSENGER)
        
        # Check profile was created automatically
        self.assertTrue(hasattr(user, 'profile'))
        
        # Login and update profile
        self.authenticate(user)
        profile_url = reverse('profile-detail', kwargs={'pk': user.profile.pk})
        profile_data = {
            'bio': 'I am a new user',
            'language': 'ar'
        }
        response = self.client.patch(profile_url, profile_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.bio, 'I am a new user')
        self.assertEqual(user.profile.language, 'ar')
    
    def test_user_permissions_flow(self):
        """Test user permissions across different user types."""
        # Admin can list all users
        self.authenticate(self.admin_user)
        url = reverse('user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Passenger can list users but only see their own
        self.authenticate(self.passenger_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Driver can list users but only see their own
        self.authenticate(self.driver_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Each user can access their own data
        for user in [self.passenger_user, self.driver_user, self.admin_user]:
            self.authenticate(user)
            user_url = reverse('user-detail', kwargs={'pk': user.pk})
            response = self.client.get(user_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            
            profile_url = reverse('profile-detail', kwargs={'pk': user.profile.pk})
            response = self.client.get(profile_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)