"""
Basic API endpoint tests for DZ Bus Tracker.
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestBasicEndpoints:
    """Test basic API endpoints."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        self.client = APIClient()
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = self.client.get('/health/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['status'] == 'healthy'
    
    def test_api_schema(self):
        """Test API schema endpoint."""
        response = self.client.get('/api/schema/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_swagger_ui(self):
        """Test Swagger UI endpoint."""
        response = self.client.get('/api/schema/swagger-ui/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_public_endpoints(self):
        """Test public endpoints that don't require authentication."""
        public_endpoints = [
            '/api/v1/buses/buses/',
            '/api/v1/drivers/drivers/',
            '/api/v1/lines/lines/',
            '/api/v1/lines/stops/',
            '/api/v1/tracking/active-buses/',
        ]
        
        for endpoint in public_endpoints:
            response = self.client.get(endpoint)
            # Should return 200 (success) or redirect, not authentication error
            assert response.status_code not in [401, 403], f"Endpoint {endpoint} requires authentication when it shouldn't"
    
    def test_protected_endpoints_require_auth(self):
        """Test that protected endpoints require authentication."""
        protected_endpoints = [
            '/api/v1/accounts/users/me/',
            '/api/v1/accounts/profile/',
        ]
        
        for endpoint in protected_endpoints:
            response = self.client.get(endpoint)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"Protected endpoint {endpoint} doesn't require authentication"
    
    def test_registration_endpoint(self):
        """Test user registration endpoint."""
        data = {
            'email': 'testuser@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'user_type': 'passenger'
        }
        
        response = self.client.post('/api/v1/accounts/register/', data)
        # Should succeed or have validation errors, not crash
        assert response.status_code in [200, 201, 400]
    
    def test_login_endpoint_structure(self):
        """Test login endpoint structure."""
        # Test with missing data to verify endpoint exists and validates
        response = self.client.post('/api/v1/accounts/login/', {})
        # Should return 400 (validation error), not 404 (not found)
        assert response.status_code != status.HTTP_404_NOT_FOUND