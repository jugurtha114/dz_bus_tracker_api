"""
Example test file to demonstrate pytest with Django.
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_user_creation():
    """Test creating a user."""
    user = User.objects.create_user(
        email='example@test.com',
        password='TestPassword123',
        first_name='Test',
        last_name='User'
    )
    assert user.email == 'example@test.com'
    assert user.check_password('TestPassword123')
    assert user.get_full_name() == 'Test User'


@pytest.mark.django_db
def test_authentication_endpoint(api_client):
    """Test authentication endpoint."""
    # Create a user
    User.objects.create_user(
        email='auth@test.com',
        password='TestPassword123'
    )
    
    # Test login
    response = api_client.post('/api/v1/accounts/login/', {
        'email': 'auth@test.com',
        'password': 'TestPassword123'
    })
    
    assert response.status_code == 200
    assert 'access' in response.data
    assert 'refresh' in response.data


def test_simple_math():
    """Test that doesn't need database."""
    assert 2 + 2 == 4