"""
Tests for lines API endpoints.
"""
import tempfile
from datetime import time
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
from apps.lines.models import Line, Stop, LineStop, Schedule
from apps.core.constants import USER_TYPE_DRIVER, USER_TYPE_PASSENGER


class LinesAPITestCase(APITestCase):
    """Base test case for lines API."""
    
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
        
        # Create stops
        self.stop1 = Stop.objects.create(
            name='Central Station',
            latitude=Decimal('36.7528'),
            longitude=Decimal('3.0424'),
            address='Algiers Central Station',
            description='Main bus station',
            features=['shelter', 'benches', 'lighting']
        )
        
        self.stop2 = Stop.objects.create(
            name='University',
            latitude=Decimal('36.7600'),
            longitude=Decimal('3.0500'),
            address='University of Algiers',
            description='University stop',
            features=['shelter', 'lighting']
        )
        
        self.stop3 = Stop.objects.create(
            name='Hospital',
            latitude=Decimal('36.7400'),
            longitude=Decimal('3.0300'),
            address='Mustapha Hospital',
            description='Hospital stop',
            features=['shelter']
        )
        
        # Create line
        self.line = Line.objects.create(
            name='Line A',
            code='LA-01',
            description='Main line connecting central areas',
            color='#FF0000',
            frequency=15
        )
        
        # Create line stops with order
        self.line_stop1 = LineStop.objects.create(
            line=self.line,
            stop=self.stop1,
            order=1,
            distance_from_previous=Decimal('0.00')
        )
        
        self.line_stop2 = LineStop.objects.create(
            line=self.line,
            stop=self.stop2,
            order=2,
            distance_from_previous=Decimal('2500.00'),
            average_time_from_previous=300  # 5 minutes
        )
        
        self.line_stop3 = LineStop.objects.create(
            line=self.line,
            stop=self.stop3,
            order=3,
            distance_from_previous=Decimal('1800.00'),
            average_time_from_previous=240  # 4 minutes
        )
        
        # Create schedule
        self.schedule = Schedule.objects.create(
            line=self.line,
            day_of_week=0,  # Monday
            start_time=time(6, 0),
            end_time=time(22, 0),
            frequency_minutes=15
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


class LineViewSetTestCase(LinesAPITestCase):
    """Test cases for LineViewSet."""
    
    def test_list_lines_unauthenticated(self):
        """Test listing lines without authentication."""
        url = reverse('line-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_lines_as_passenger(self):
        """Test listing lines as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('line-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_list_lines_as_driver(self):
        """Test listing lines as driver."""
        self.authenticate(self.driver_user)
        url = reverse('line-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_lines_as_admin(self):
        """Test listing lines as admin."""
        self.authenticate(self.admin_user)
        url = reverse('line-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_line(self):
        """Test retrieving line."""
        self.authenticate(self.passenger_user)
        url = reverse('line-detail', kwargs={'pk': self.line.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['code'], self.line.code)
        self.assertEqual(response.data['name'], self.line.name)
    
    def test_create_line_as_admin(self):
        """Test creating line as admin."""
        self.authenticate(self.admin_user)
        url = reverse('line-list')
        data = {
            'name': 'Line B',
            'code': 'LB-01',
            'description': 'Secondary line',
            'color': '#00FF00',
            'frequency': 20
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Line.objects.filter(code='LB-01').exists())
    
    def test_create_line_as_passenger(self):
        """Test creating line as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('line-list')
        data = {
            'name': 'Line B',
            'code': 'LB-01',
            'description': 'Secondary line'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_line_duplicate_code(self):
        """Test creating line with duplicate code."""
        self.authenticate(self.admin_user)
        url = reverse('line-list')
        data = {
            'name': 'Another Line A',
            'code': 'LA-01',  # Same as existing line
            'description': 'Duplicate code line'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_line_as_admin(self):
        """Test updating line as admin."""
        self.authenticate(self.admin_user)
        url = reverse('line-detail', kwargs={'pk': self.line.pk})
        data = {
            'name': 'Updated Line A',
            'description': 'Updated description',
            'frequency': 12,
            'color': '#0000FF'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.line.refresh_from_db()
        self.assertEqual(self.line.name, 'Updated Line A')
        self.assertEqual(self.line.frequency, 12)
        self.assertEqual(self.line.color, '#0000FF')
    
    def test_update_line_as_driver(self):
        """Test updating line as driver."""
        self.authenticate(self.driver_user)
        url = reverse('line-detail', kwargs={'pk': self.line.pk})
        data = {'name': 'Hacked Line'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_line_as_admin(self):
        """Test deleting line as admin."""
        self.authenticate(self.admin_user)
        url = reverse('line-detail', kwargs={'pk': self.line.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.line.refresh_from_db()
        self.assertFalse(self.line.is_active)
    
    def test_search_lines(self):
        """Test searching lines."""
        self.authenticate(self.passenger_user)
        url = reverse('line-list')
        
        # Search by name
        response = self.client.get(url, {'search': 'Line A'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
        
        # Search by code
        response = self.client.get(url, {'search': 'LA-01'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_filter_lines_by_active(self):
        """Test filtering lines by active status."""
        # Create inactive line
        inactive_line = Line.objects.create(
            name='Inactive Line',
            code='IL-01',
            is_active=False
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('line-list')
        
        # Filter active lines
        response = self.client.get(url, {'is_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for line in response.data['results']:
            self.assertTrue(line['is_active'])


class StopViewSetTestCase(LinesAPITestCase):
    """Test cases for StopViewSet."""
    
    def test_list_stops_unauthenticated(self):
        """Test listing stops without authentication."""
        url = reverse('stop-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_stops_as_passenger(self):
        """Test listing stops as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('stop-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    def test_retrieve_stop(self):
        """Test retrieving stop."""
        self.authenticate(self.passenger_user)
        url = reverse('stop-detail', kwargs={'pk': self.stop1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.stop1.name)
        self.assertEqual(float(response.data['latitude']), float(self.stop1.latitude))
    
    def test_create_stop_as_admin(self):
        """Test creating stop as admin."""
        self.authenticate(self.admin_user)
        url = reverse('stop-list')
        data = {
            'name': 'New Stop',
            'latitude': '36.7700',
            'longitude': '3.0600',
            'address': 'New Stop Address',
            'description': 'New stop description',
            'features': ['shelter', 'wifi']
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Stop.objects.filter(name='New Stop').exists())
    
    def test_create_stop_as_passenger(self):
        """Test creating stop as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('stop-list')
        data = {
            'name': 'Passenger Stop',
            'latitude': '36.7700',
            'longitude': '3.0600'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_stop_invalid_coordinates(self):
        """Test creating stop with invalid coordinates."""
        self.authenticate(self.admin_user)
        url = reverse('stop-list')
        data = {
            'name': 'Invalid Stop',
            'latitude': '91.0000',  # Invalid: > 90
            'longitude': '181.0000'  # Invalid: > 180
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_stop_as_admin(self):
        """Test updating stop as admin."""
        self.authenticate(self.admin_user)
        url = reverse('stop-detail', kwargs={'pk': self.stop1.pk})
        data = {
            'name': 'Updated Central Station',
            'description': 'Updated description',
            'features': ['shelter', 'benches', 'lighting', 'wifi']
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stop1.refresh_from_db()
        self.assertEqual(self.stop1.name, 'Updated Central Station')
        self.assertIn('wifi', self.stop1.features)
    
    def test_update_stop_photo(self):
        """Test updating stop photo."""
        self.authenticate(self.admin_user)
        url = reverse('stop-detail', kwargs={'pk': self.stop1.pk})
        test_image = self.create_test_image()
        data = {'photo': test_image}
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stop1.refresh_from_db()
        self.assertTrue(self.stop1.photo)
    
    def test_delete_stop_as_admin(self):
        """Test deleting stop as admin."""
        self.authenticate(self.admin_user)
        url = reverse('stop-detail', kwargs={'pk': self.stop1.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.stop1.refresh_from_db()
        self.assertFalse(self.stop1.is_active)
    
    def test_search_stops(self):
        """Test searching stops."""
        self.authenticate(self.passenger_user)
        url = reverse('stop-list')
        
        # Search by name
        response = self.client.get(url, {'search': 'Central'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
        
        # Search by address
        response = self.client.get(url, {'search': 'Algiers'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_filter_stops_by_location(self):
        """Test filtering stops by location (if implemented)."""
        self.authenticate(self.passenger_user)
        url = reverse('stop-list')
        
        # This test assumes there might be location-based filtering
        # The actual implementation depends on the API design
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ScheduleViewSetTestCase(LinesAPITestCase):
    """Test cases for ScheduleViewSet."""
    
    def test_list_schedules_unauthenticated(self):
        """Test listing schedules without authentication."""
        url = reverse('schedule-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_schedules_as_passenger(self):
        """Test listing schedules as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('schedule-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_retrieve_schedule(self):
        """Test retrieving schedule."""
        self.authenticate(self.passenger_user)
        url = reverse('schedule-detail', kwargs={'pk': self.schedule.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['day_of_week'], self.schedule.day_of_week)
        self.assertEqual(response.data['frequency_minutes'], self.schedule.frequency_minutes)
    
    def test_create_schedule_as_admin(self):
        """Test creating schedule as admin."""
        self.authenticate(self.admin_user)
        url = reverse('schedule-list')
        data = {
            'line': self.line.pk,
            'day_of_week': 1,  # Tuesday
            'start_time': '07:00:00',
            'end_time': '21:00:00',
            'frequency_minutes': 20
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Schedule.objects.filter(
            line=self.line,
            day_of_week=1
        ).exists())
    
    def test_create_schedule_as_passenger(self):
        """Test creating schedule as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('schedule-list')
        data = {
            'line': self.line.pk,
            'day_of_week': 2,
            'start_time': '08:00:00',
            'end_time': '20:00:00',
            'frequency_minutes': 25
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_schedule_invalid_time(self):
        """Test creating schedule with invalid time."""
        self.authenticate(self.admin_user)
        url = reverse('schedule-list')
        data = {
            'line': self.line.pk,
            'day_of_week': 2,
            'start_time': '22:00:00',  # Start after end
            'end_time': '06:00:00',
            'frequency_minutes': 15
        }
        response = self.client.post(url, data)
        # This should be validated at the serializer/model level
        # The exact status code depends on implementation
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST])
    
    def test_create_duplicate_schedule(self):
        """Test creating duplicate schedule."""
        self.authenticate(self.admin_user)
        url = reverse('schedule-list')
        data = {
            'line': self.line.pk,
            'day_of_week': 0,  # Same as existing
            'start_time': '06:00:00',  # Same as existing
            'end_time': '23:00:00',
            'frequency_minutes': 10
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_schedule_as_admin(self):
        """Test updating schedule as admin."""
        self.authenticate(self.admin_user)
        url = reverse('schedule-detail', kwargs={'pk': self.schedule.pk})
        data = {
            'end_time': '23:30:00',
            'frequency_minutes': 12
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.end_time, time(23, 30))
        self.assertEqual(self.schedule.frequency_minutes, 12)
    
    def test_delete_schedule_as_admin(self):
        """Test deleting schedule as admin."""
        self.authenticate(self.admin_user)
        url = reverse('schedule-detail', kwargs={'pk': self.schedule.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_active)
    
    def test_filter_schedules_by_line(self):
        """Test filtering schedules by line."""
        # Create another line and schedule
        another_line = Line.objects.create(
            name='Line B',
            code='LB-01',
            description='Another line'
        )
        Schedule.objects.create(
            line=another_line,
            day_of_week=1,
            start_time=time(8, 0),
            end_time=time(20, 0),
            frequency_minutes=30
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('schedule-list')
        
        # Filter by original line
        response = self.client.get(url, {'line': self.line.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for schedule in response.data['results']:
            self.assertEqual(schedule['line'], str(self.line.pk))
    
    def test_filter_schedules_by_day(self):
        """Test filtering schedules by day of week."""
        # Create schedule for different day
        Schedule.objects.create(
            line=self.line,
            day_of_week=6,  # Sunday
            start_time=time(8, 0),
            end_time=time(18, 0),
            frequency_minutes=30
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('schedule-list')
        
        # Filter by Monday
        response = self.client.get(url, {'day_of_week': 0})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for schedule in response.data['results']:
            self.assertEqual(schedule['day_of_week'], 0)


class LinesAPIIntegrationTestCase(LinesAPITestCase):
    """Integration tests for lines API."""
    
    def test_complete_line_setup_flow(self):
        """Test complete line setup flow."""
        self.authenticate(self.admin_user)
        
        # Create new line
        line_url = reverse('line-list')
        line_data = {
            'name': 'Express Line',
            'code': 'EX-01',
            'description': 'Express service',
            'color': '#FF8000',
            'frequency': 10
        }
        response = self.client.post(line_url, line_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_line_id = response.data['id']
        
        # Create stops for the line
        stop_url = reverse('stop-list')
        stops_data = [
            {
                'name': 'Express Start',
                'latitude': '36.7800',
                'longitude': '3.0700',
                'address': 'Express starting point'
            },
            {
                'name': 'Express Middle',
                'latitude': '36.7850',
                'longitude': '3.0750',
                'address': 'Express middle point'
            },
            {
                'name': 'Express End',
                'latitude': '36.7900',
                'longitude': '3.0800',
                'address': 'Express ending point'
            }
        ]
        
        created_stops = []
        for stop_data in stops_data:
            response = self.client.post(stop_url, stop_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            created_stops.append(response.data['id'])
        
        # Create schedules for the line
        schedule_url = reverse('schedule-list')
        schedules_data = [
            {
                'line': new_line_id,
                'day_of_week': 0,  # Monday
                'start_time': '05:30:00',
                'end_time': '23:00:00',
                'frequency_minutes': 10
            },
            {
                'line': new_line_id,
                'day_of_week': 6,  # Sunday
                'start_time': '07:00:00',
                'end_time': '21:00:00',
                'frequency_minutes': 15
            }
        ]
        
        for schedule_data in schedules_data:
            response = self.client.post(schedule_url, schedule_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify line is accessible to passengers
        self.authenticate(self.passenger_user)
        response = self.client.get(line_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        line_codes = [line['code'] for line in response.data['results']]
        self.assertIn('EX-01', line_codes)
        
        # Verify stops are accessible
        response = self.client.get(stop_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stop_names = [stop['name'] for stop in response.data['results']]
        self.assertIn('Express Start', stop_names)
        
        # Verify schedules are accessible
        response = self.client.get(schedule_url, {'line': new_line_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_line_search_and_filtering_flow(self):
        """Test line search and filtering flow."""
        # Create additional test data
        self.authenticate(self.admin_user)
        
        # Create night line
        night_line = Line.objects.create(
            name='Night Express',
            code='NE-01',
            description='Night service',
            color='#000080',
            frequency=30
        )
        
        # Create schedule for night line
        Schedule.objects.create(
            line=night_line,
            day_of_week=5,  # Saturday
            start_time=time(23, 0),
            end_time=time(5, 0),
            frequency_minutes=30
        )
        
        # Create inactive line
        inactive_line = Line.objects.create(
            name='Old Line',
            code='OL-01',
            description='Discontinued service',
            is_active=False
        )
        
        # Test as passenger
        self.authenticate(self.passenger_user)
        
        # Search lines by name
        line_url = reverse('line-list')
        response = self.client.get(line_url, {'search': 'Express'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        found_names = [line['name'] for line in response.data['results']]
        self.assertIn('Night Express', found_names)
        
        # Search lines by code
        response = self.client.get(line_url, {'search': 'NE-01'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
        
        # Filter active lines only
        response = self.client.get(line_url, {'is_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for line in response.data['results']:
            self.assertTrue(line['is_active'])
        
        # Test schedule filtering
        schedule_url = reverse('schedule-list')
        response = self.client.get(schedule_url, {'day_of_week': 5})  # Saturday
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for schedule in response.data['results']:
            self.assertEqual(schedule['day_of_week'], 5)
    
    def test_permissions_across_line_management(self):
        """Test permissions across line management operations."""
        # Admin can do everything
        self.authenticate(self.admin_user)
        
        # Create line
        line_url = reverse('line-list')
        line_data = {'name': 'Admin Line', 'code': 'AL-01'}
        response = self.client.post(line_url, line_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        admin_line_id = response.data['id']
        
        # Create stop
        stop_url = reverse('stop-list')
        stop_data = {
            'name': 'Admin Stop',
            'latitude': '36.7000',
            'longitude': '3.0000'
        }
        response = self.client.post(stop_url, stop_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Create schedule
        schedule_url = reverse('schedule-list')
        schedule_data = {
            'line': admin_line_id,
            'day_of_week': 3,
            'start_time': '06:00:00',
            'end_time': '22:00:00',
            'frequency_minutes': 20
        }
        response = self.client.post(schedule_url, schedule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Driver can read but not modify
        self.authenticate(self.driver_user)
        
        # Can read lines
        response = self.client.get(line_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Cannot create lines
        response = self.client.post(line_url, {'name': 'Driver Line', 'code': 'DL-01'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Cannot modify lines
        admin_line_url = reverse('line-detail', kwargs={'pk': admin_line_id})
        response = self.client.patch(admin_line_url, {'name': 'Modified'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Passenger can read but not modify
        self.authenticate(self.passenger_user)
        
        # Can read all entities
        for url in [line_url, stop_url, schedule_url]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Cannot create/modify anything
        for url in [line_url, stop_url, schedule_url]:
            response = self.client.post(url, {})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)