"""
Comprehensive JWT authentication and security testing for DZ Bus Tracker.
Tests all authentication flows, JWT token handling, and security measures.
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from django.contrib.auth import get_user_model
from django.core import mail
from unittest.mock import patch

from apps.accounts.models import Profile
from apps.drivers.models import Driver

User = get_user_model()


@pytest.mark.django_db
class TestJWTAuthentication:
    """Test JWT authentication functionality."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            user_type='passenger'
        )
        
        self.driver_user = User.objects.create_user(
            email='driver@example.com',
            password='testpass123',
            first_name='Test',
            last_name='Driver',
            user_type='driver'
        )
        
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='testpass123',
            first_name='Admin',
            last_name='User'
        )
    
    def test_token_obtain_valid_credentials(self):
        """Test obtaining tokens with valid credentials."""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        response = self.client.post('/api/token/', data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
        
        # Verify token structure
        access_token = response.data['access']
        refresh_token = response.data['refresh']
        
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        assert len(access_token.split('.')) == 3  # JWT has 3 parts
        assert len(refresh_token.split('.')) == 3
    
    def test_token_obtain_invalid_credentials(self):
        """Test obtaining tokens with invalid credentials."""
        test_cases = [
            # Wrong password
            {'email': 'test@example.com', 'password': 'wrongpass'},
            # Wrong email
            {'email': 'wrong@example.com', 'password': 'testpass123'},
            # Non-existent user
            {'email': 'nonexistent@example.com', 'password': 'testpass123'},
            # Empty email
            {'email': '', 'password': 'testpass123'},
            # Empty password
            {'email': 'test@example.com', 'password': ''},
            # Missing email
            {'password': 'testpass123'},
            # Missing password
            {'email': 'test@example.com'},
        ]
        
        for data in test_cases:
            response = self.client.post('/api/token/', data)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED
            ]
            assert 'access' not in response.data
    
    def test_token_refresh_valid(self):
        """Test refreshing tokens with valid refresh token."""
        # Get initial tokens
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        refresh_token = response.data['refresh']
        
        # Refresh the token
        refresh_data = {'refresh': refresh_token}
        response = self.client.post('/api/token/refresh/', refresh_data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        
        # Verify new access token is different
        new_access_token = response.data['access']
        assert isinstance(new_access_token, str)
        assert len(new_access_token.split('.')) == 3
    
    def test_token_refresh_invalid(self):
        """Test refreshing tokens with invalid refresh token."""
        test_cases = [
            # Invalid token format
            {'refresh': 'invalid_token'},
            # Empty token
            {'refresh': ''},
            # Missing token
            {},
            # Expired token (simulated)
            {'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.invalid.signature'},
        ]
        
        for data in test_cases:
            response = self.client.post('/api/token/refresh/', data)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED
            ]
    
    def test_token_verify_valid(self):
        """Test verifying valid tokens."""
        # Get access token
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        access_token = response.data['access']
        
        # Verify the token
        verify_data = {'token': access_token}
        response = self.client.post('/api/token/verify/', verify_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_token_verify_invalid(self):
        """Test verifying invalid tokens."""
        test_cases = [
            # Invalid token format
            {'token': 'invalid_token'},
            # Empty token
            {'token': ''},
            # Missing token
            {},
            # Malformed JWT
            {'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.invalid'},
        ]
        
        for data in test_cases:
            response = self.client.post('/api/token/verify/', data)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED
            ]
    
    def test_token_blacklisting(self):
        """Test token blacklisting functionality."""
        # Get tokens
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        refresh_token = response.data['refresh']
        
        # Use the refresh token
        refresh_data = {'refresh': refresh_token}
        response = self.client.post('/api/token/refresh/', refresh_data)
        assert response.status_code == status.HTTP_200_OK
        
        # Logout (blacklist the token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        logout_data = {'refresh': refresh_token}
        response = self.client.post('/api/v1/accounts/users/logout/', logout_data)
        assert response.status_code == status.HTTP_200_OK
        
        # Try to use the blacklisted refresh token
        response = self.client.post('/api/token/refresh/', refresh_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_access_token_authentication(self):
        """Test accessing protected endpoints with access tokens."""
        # Get access token
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        access_token = response.data['access']
        
        # Access protected endpoint without token
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # Access protected endpoint with valid token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == 'test@example.com'
        
        # Clear credentials
        self.client.credentials()
        
        # Access with invalid token format
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid_token')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # Access with wrong authorization header format
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {access_token}')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_token_user_claims(self):
        """Test that tokens contain correct user information."""
        # Get tokens for different user types
        users = [
            ('test@example.com', self.user),
            ('driver@example.com', self.driver_user),
            ('admin@example.com', self.admin_user),
        ]
        
        for email, user in users:
            data = {'email': email, 'password': 'testpass123'}
            response = self.client.post('/api/token/', data)
            access_token = response.data['access']
            
            # Use token to access user info
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
            response = self.client.get('/api/v1/accounts/users/me/')
            
            assert response.status_code == status.HTTP_200_OK
            assert response.data['email'] == email
            assert response.data['id'] == str(user.id)
            assert response.data['user_type'] == user.user_type
            
            self.client.credentials()  # Clear credentials
    
    def test_concurrent_token_usage(self):
        """Test using multiple tokens for the same user."""
        # Get first set of tokens
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response1 = self.client.post('/api/token/', data)
        access_token1 = response1.data['access']
        
        # Get second set of tokens
        response2 = self.client.post('/api/token/', data)
        access_token2 = response2.data['access']
        
        # Both tokens should work
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token1}')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_200_OK
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token2}')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_inactive_user_token_rejection(self):
        """Test that inactive users cannot get or use tokens."""
        # Deactivate user
        self.user.is_active = False
        self.user.save()
        
        # Try to get token for inactive user
        data = {'email': 'test@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/token/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # Reactivate user and get token
        self.user.is_active = True
        self.user.save()
        
        response = self.client.post('/api/token/', data)
        access_token = response.data['access']
        
        # Deactivate user again
        self.user.is_active = False
        self.user.save()
        
        # Try to use existing token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get('/api/v1/accounts/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserRegistrationLogin:
    """Test user registration and login flows."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
    
    def test_user_registration_success(self):
        """Test successful user registration."""
        data = {
            'email': 'newuser@example.com',
            'password': 'newpass123',
            'password_confirm': 'newpass123',
            'first_name': 'New',
            'last_name': 'User',
            'user_type': 'passenger'
        }
        
        response = self.client.post('/api/v1/accounts/register/', data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'access' in response.data
        assert 'refresh' in response.data
        
        # Verify user was created
        user = User.objects.get(email='newuser@example.com')
        assert user.first_name == 'New'
        assert user.last_name == 'User'
        assert user.user_type == 'passenger'
        assert user.is_active is True
        
        # Verify profile was created
        assert hasattr(user, 'profile')
        assert user.profile is not None
    
    def test_user_registration_validation(self):
        """Test user registration validation."""
        # Create existing user
        User.objects.create_user(
            email='existing@example.com',
            password='testpass123'
        )
        
        test_cases = [
            # Duplicate email
            {
                'data': {
                    'email': 'existing@example.com',
                    'password': 'newpass123',
                    'password_confirm': 'newpass123',
                    'first_name': 'New',
                    'last_name': 'User',
                    'user_type': 'passenger'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Password mismatch
            {
                'data': {
                    'email': 'newuser@example.com',
                    'password': 'newpass123',
                    'password_confirm': 'differentpass',
                    'first_name': 'New',
                    'last_name': 'User',
                    'user_type': 'passenger'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Invalid email format
            {
                'data': {
                    'email': 'invalid-email',
                    'password': 'newpass123',
                    'password_confirm': 'newpass123',
                    'first_name': 'New',
                    'last_name': 'User',
                    'user_type': 'passenger'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Missing required fields
            {
                'data': {
                    'email': 'newuser@example.com',
                    'password': 'newpass123',
                    'password_confirm': 'newpass123',
                    # Missing first_name, last_name
                    'user_type': 'passenger'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Invalid user type
            {
                'data': {
                    'email': 'newuser@example.com',
                    'password': 'newpass123',
                    'password_confirm': 'newpass123',
                    'first_name': 'New',
                    'last_name': 'User',
                    'user_type': 'invalid_type'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
        ]
        
        for test_case in test_cases:
            response = self.client.post('/api/v1/accounts/register/', test_case['data'])
            assert response.status_code == test_case['expected_status']
    
    def test_driver_registration_success(self):
        """Test successful driver registration."""
        data = {
            'email': 'newdriver@example.com',
            'password': 'newpass123',
            'password_confirm': 'newpass123',
            'first_name': 'New',
            'last_name': 'Driver',
            'phone_number': '+213555123456',
            'id_card_number': '123456789',
            'driver_license_number': 'DL123456',
            'years_of_experience': 5
        }
        
        response = self.client.post('/api/v1/accounts/register-driver/', data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'driver_id' in response.data
        assert 'access' in response.data
        assert 'refresh' in response.data
        
        # Verify user was created
        user = User.objects.get(email='newdriver@example.com')
        assert user.user_type == 'driver'
        
        # Verify driver profile was created
        driver = Driver.objects.get(user=user)
        assert driver.phone_number == '+213555123456'
        assert driver.id_card_number == '123456789'
        assert driver.driver_license_number == 'DL123456'
        assert driver.years_of_experience == 5
        assert driver.status == 'pending'  # Default status
    
    def test_user_login_success(self):
        """Test successful user login."""
        # Create user
        user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        data = {
            'email': 'testuser@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/accounts/login/', data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'user' in response.data
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == 'testuser@example.com'
    
    def test_user_login_validation(self):
        """Test user login validation."""
        # Create user
        User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )
        
        test_cases = [
            # Wrong password
            {
                'data': {'email': 'testuser@example.com', 'password': 'wrongpass'},
                'expected_status': status.HTTP_401_UNAUTHORIZED
            },
            # Wrong email
            {
                'data': {'email': 'wrong@example.com', 'password': 'testpass123'},
                'expected_status': status.HTTP_401_UNAUTHORIZED
            },
            # Missing email
            {
                'data': {'password': 'testpass123'},
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Missing password
            {
                'data': {'email': 'testuser@example.com'},
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Empty credentials
            {
                'data': {'email': '', 'password': ''},
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
        ]
        
        for test_case in test_cases:
            response = self.client.post('/api/v1/accounts/login/', test_case['data'])
            assert response.status_code == test_case['expected_status']
    
    def test_inactive_user_login(self):
        """Test that inactive users cannot login."""
        # Create inactive user
        user = User.objects.create_user(
            email='inactive@example.com',
            password='testpass123',
            is_active=False
        )
        
        data = {
            'email': 'inactive@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/accounts/login/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_logout_functionality(self):
        """Test user logout functionality."""
        # Create user and login
        user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )
        
        data = {'email': 'testuser@example.com', 'password': 'testpass123'}
        response = self.client.post('/api/v1/accounts/login/', data)
        refresh_token = response.data['refresh']
        access_token = response.data['access']
        
        # Authenticate with access token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        # Logout
        logout_data = {'refresh': refresh_token}
        response = self.client.post('/api/v1/accounts/users/logout/', logout_data)
        assert response.status_code == status.HTTP_200_OK
        
        # Try to refresh with blacklisted token
        response = self.client.post('/api/token/refresh/', {'refresh': refresh_token})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPasswordSecurity:
    """Test password security and reset functionality."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            email='test@example.com',
            password='oldpass123',
            first_name='Test',
            last_name='User'
        )
    
    def test_password_change_success(self):
        """Test successful password change."""
        # Authenticate user
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        data = {
            'old_password': 'oldpass123',
            'new_password': 'newpass123',
            'new_password_confirm': 'newpass123'
        }
        
        response = self.client.post(f'/api/v1/accounts/users/{self.user.id}/change_password/', data)
        assert response.status_code == status.HTTP_200_OK
        
        # Verify password was changed
        self.user.refresh_from_db()
        assert self.user.check_password('newpass123')
        assert not self.user.check_password('oldpass123')
    
    def test_password_change_validation(self):
        """Test password change validation."""
        # Authenticate user
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        test_cases = [
            # Wrong old password
            {
                'data': {
                    'old_password': 'wrongpass',
                    'new_password': 'newpass123',
                    'new_password_confirm': 'newpass123'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # New password mismatch
            {
                'data': {
                    'old_password': 'oldpass123',
                    'new_password': 'newpass123',
                    'new_password_confirm': 'differentpass'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
            # Same as old password
            {
                'data': {
                    'old_password': 'oldpass123',
                    'new_password': 'oldpass123',
                    'new_password_confirm': 'oldpass123'
                },
                'expected_status': status.HTTP_400_BAD_REQUEST
            },
        ]
        
        for test_case in test_cases:
            response = self.client.post(
                f'/api/v1/accounts/users/{self.user.id}/change_password/',
                test_case['data']
            )
            assert response.status_code == test_case['expected_status']
    
    def test_password_reset_request(self):
        """Test password reset request."""
        data = {'email': 'test@example.com'}
        
        with patch('apps.accounts.services.UserService.generate_password_reset_token') as mock_token:
            mock_token.return_value = {'uid': 'test_uid', 'token': 'test_token'}
            
            response = self.client.post('/api/v1/accounts/users/reset_password_request/', data)
            assert response.status_code == status.HTTP_200_OK
            mock_token.assert_called_once()
    
    def test_password_reset_nonexistent_email(self):
        """Test password reset for non-existent email."""
        data = {'email': 'nonexistent@example.com'}
        
        response = self.client.post('/api/v1/accounts/users/reset_password_request/', data)
        # Should return 200 even for non-existent emails (security best practice)
        assert response.status_code == status.HTTP_200_OK


def run_authentication_tests():
    """Run all authentication tests and return results."""
    import subprocess
    import sys
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            '/home/shared/projects/PycharmProjects/dz_bus_tracker_v2/tests/api/test_authentication_jwt.py',
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
    result = run_authentication_tests()
    print(result['stdout'])
    if result['stderr']:
        print("STDERR:", result['stderr'])
    sys.exit(result['returncode'])