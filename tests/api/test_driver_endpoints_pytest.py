"""
Test driver endpoints using pytest.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from apps.drivers.models import Driver

User = get_user_model()


@pytest.mark.django_db
class TestDriverEndpoints:
    """Test driver API endpoints."""
    
    def test_driver_registration(self):
        """Test driver registration endpoint."""
        client = APIClient()
        
        data = {
            'email': 'newdriver@test.com',
            'password': 'Test1234',
            'confirm_password': 'Test1234',
            'first_name': 'New',
            'last_name': 'Driver',
            'phone_number': '+213555123456',
            'id_card_number': '123456789',
            'id_card_photo': None,  # Would be a file in real test
            'driver_license_number': 'DL123456',
            'driver_license_photo': None,  # Would be a file in real test
            'years_of_experience': 5
        }
        
        response = client.post('/api/v1/drivers/register/', data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'driver_id' in response.data
    
    def test_driver_approval(self, admin_client):
        """Test driver approval by admin."""
        # Create a pending driver
        user = User.objects.create_user(
            email='pendingdriver@test.com',
            password='Test1234',
            first_name='Pending',
            last_name='Driver',
            user_type='driver'
        )
        driver = Driver.objects.create(
            user=user,
            phone_number='+213555999888',
            id_card_number='987654321',
            driver_license_number='DL987654',
            years_of_experience=3,
            status='pending'
        )
        
        # Approve the driver
        response = admin_client.patch(
            f'/api/v1/drivers/{driver.id}/',
            {'status': 'approved'},
            format='json'
        )
        
        # Check if successful
        if response.status_code == status.HTTP_404_NOT_FOUND:
            # Try the drivers endpoint (if using nested route)
            response = admin_client.patch(
                f'/api/v1/drivers/drivers/{driver.id}/',
                {'status': 'approved'},
                format='json'
            )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify driver is approved
        driver.refresh_from_db()
        assert driver.status == 'approved'
    
    def test_driver_list(self, authenticated_client):
        """Test listing drivers."""
        response = authenticated_client.get('/api/v1/drivers/')
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data or isinstance(response.data, list)
    
    def test_driver_detail(self, authenticated_client, test_driver):
        """Test getting driver details."""
        response = authenticated_client.get(f'/api/v1/drivers/{test_driver.id}/')
        
        # Handle both direct and nested routes
        if response.status_code == status.HTTP_404_NOT_FOUND:
            response = authenticated_client.get(f'/api/v1/drivers/drivers/{test_driver.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(test_driver.id)