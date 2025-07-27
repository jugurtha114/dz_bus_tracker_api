"""
Pytest configuration and fixtures for DZ Bus Tracker tests.
"""
import os
import sys
import django
import pytest
from django.conf import settings
from django.test import TestCase

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an API client instance."""
    return APIClient()


@pytest.fixture
def test_user():
    """Create a test user."""
    user = User.objects.create_user(
        email='testuser@example.com',
        password='testpass123',
        first_name='Test',
        last_name='User',
        user_type='passenger'
    )
    return user


@pytest.fixture
def test_driver():
    """Create a test driver user."""
    user = User.objects.create_user(
        email='testdriver@example.com',
        password='testpass123',
        first_name='Test',
        last_name='Driver',
        user_type='driver'
    )
    # Create driver profile
    from apps.drivers.models import Driver
    driver = Driver.objects.create(
        user=user,
        phone_number='+213555123456',
        id_card_number='123456789',
        driver_license_number='DL123456',
        years_of_experience=5,
        status='approved'
    )
    return driver


@pytest.fixture
def test_admin():
    """Create a test admin user."""
    user = User.objects.create_superuser(
        email='testadmin@example.com',
        password='testpass123',
        first_name='Test',
        last_name='Admin'
    )
    return user


@pytest.fixture
def authenticated_client(api_client, test_user):
    """Return an authenticated API client."""
    refresh = RefreshToken.for_user(test_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def driver_client(api_client, test_driver):
    """Return an authenticated driver API client."""
    refresh = RefreshToken.for_user(test_driver.user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def admin_client(api_client, test_admin):
    """Return an authenticated admin API client."""
    refresh = RefreshToken.for_user(test_admin)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Give all tests access to the database.
    """
    pass


@pytest.fixture
def sample_bus():
    """Create a sample bus."""
    from apps.buses.models import Bus
    from apps.drivers.models import Driver
    
    # Get or create a driver
    driver = Driver.objects.first()
    if not driver:
        user = User.objects.create_user(
            email='busdriver@example.com',
            password='testpass123',
            first_name='Bus',
            last_name='Driver',
            user_type='driver'
        )
        driver = Driver.objects.create(
            user=user,
            phone_number='+213555999888',
            id_card_number='987654321',
            driver_license_number='DL987654',
            years_of_experience=10,
            status='approved'
        )
    
    bus = Bus.objects.create(
        bus_number='B001',
        license_plate='16-12345-113',
        driver=driver,
        model='Mercedes Sprinter',
        manufacturer='Mercedes-Benz',
        year=2020,
        capacity=30,
        status='active',
        is_active=True,
        is_approved=True
    )
    return bus


@pytest.fixture
def sample_line():
    """Create a sample line."""
    from apps.lines.models import Line
    
    line = Line.objects.create(
        name='Line 1',
        code='L1',
        description='Test line from A to B',
        is_active=True,
        color='#FF0000'
    )
    return line


@pytest.fixture
def sample_stops():
    """Create sample stops."""
    from apps.lines.models import Stop
    
    stops = []
    for i in range(3):
        stop = Stop.objects.create(
            name=f'Stop {i+1}',
            latitude=36.7 + (i * 0.01),
            longitude=3.0 + (i * 0.01),
            address=f'Address {i+1}',
            is_active=True
        )
        stops.append(stop)
    return stops