"""
Tests for tracking API endpoints.
"""
import uuid
from datetime import datetime, time
from decimal import Decimal
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, Profile
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import (
    BusLine, LocationUpdate, PassengerCount, 
    WaitingPassengers, Trip, Anomaly
)
from apps.core.constants import (
    USER_TYPE_DRIVER, USER_TYPE_PASSENGER, 
    DRIVER_STATUS_APPROVED, BUS_STATUS_ACTIVE,
    BUS_TRACKING_STATUS_IDLE, BUS_TRACKING_STATUS_ACTIVE
)


class TrackingAPITestCase(APITestCase):
    """Base test case for tracking API."""
    
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
            id_card_photo='test.jpg',
            driver_license_number='DL123456',
            driver_license_photo='test.jpg',
            status=DRIVER_STATUS_APPROVED,
            years_of_experience=5
        )
        
        # Create bus
        self.bus = Bus.objects.create(
            license_plate='ABC123DZ',
            driver=self.driver,
            model='Mercedes Sprinter',
            manufacturer='Mercedes-Benz',
            year=2020,
            capacity=25,
            status=BUS_STATUS_ACTIVE,
            is_approved=True
        )
        
        # Create line and stops
        self.line = Line.objects.create(
            name='Line A',
            code='LA-01',
            description='Main line',
            frequency=15
        )
        
        self.stop1 = Stop.objects.create(
            name='Stop 1',
            latitude=Decimal('36.7528'),
            longitude=Decimal('3.0424')
        )
        
        self.stop2 = Stop.objects.create(
            name='Stop 2',
            latitude=Decimal('36.7600'),
            longitude=Decimal('3.0500')
        )
        
        # Create bus-line assignment
        self.bus_line = BusLine.objects.create(
            bus=self.bus,
            line=self.line,
            tracking_status=BUS_TRACKING_STATUS_IDLE
        )
        
        # Create location update
        self.location_update = LocationUpdate.objects.create(
            bus=self.bus,
            latitude=Decimal('36.7528'),
            longitude=Decimal('3.0424'),
            speed=Decimal('45.50'),
            heading=Decimal('180.0'),
            accuracy=Decimal('5.0'),
            line=self.line,
            nearest_stop=self.stop1,
            distance_to_stop=Decimal('50.0')
        )
        
        # Create passenger count
        self.passenger_count = PassengerCount.objects.create(
            bus=self.bus,
            count=15,
            capacity=25,
            occupancy_rate=Decimal('0.60'),
            line=self.line,
            stop=self.stop1
        )
        
        # Create waiting passengers
        self.waiting_passengers = WaitingPassengers.objects.create(
            stop=self.stop1,
            line=self.line,
            count=8,
            reported_by=self.passenger_user
        )
        
        # Create trip
        self.trip = Trip.objects.create(
            bus=self.bus,
            driver=self.driver,
            line=self.line,
            start_time=timezone.now(),
            start_stop=self.stop1,
            distance=Decimal('12.5'),
            average_speed=Decimal('35.0'),
            max_passengers=20,
            total_stops=5
        )
        
        # Create anomaly
        self.anomaly = Anomaly.objects.create(
            bus=self.bus,
            trip=self.trip,
            type='speed',
            description='Excessive speed detected',
            severity='medium',
            location_latitude=Decimal('36.7500'),
            location_longitude=Decimal('3.0400')
        )
    
    def get_jwt_token(self, user):
        """Get JWT token for user."""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    
    def authenticate(self, user):
        """Authenticate user."""
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class BusLineViewSetTestCase(TrackingAPITestCase):
    """Test cases for BusLineViewSet."""
    
    def test_list_bus_lines_unauthenticated(self):
        """Test listing bus lines without authentication."""
        url = reverse('busline-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_bus_lines_as_passenger(self):
        """Test listing bus lines as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('busline-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_retrieve_bus_line(self):
        """Test retrieving bus line."""
        self.authenticate(self.passenger_user)
        url = reverse('busline-detail', kwargs={'pk': self.bus_line.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tracking_status'], self.bus_line.tracking_status)
    
    def test_create_bus_line_as_admin(self):
        """Test creating bus line as admin."""
        # Create another line for assignment
        another_line = Line.objects.create(
            name='Line B',
            code='LB-01',
            description='Secondary line'
        )
        
        self.authenticate(self.admin_user)
        url = reverse('busline-list')
        data = {
            'bus': self.bus.pk,
            'line': another_line.pk,
            'tracking_status': BUS_TRACKING_STATUS_IDLE
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BusLine.objects.filter(
            bus=self.bus,
            line=another_line
        ).exists())
    
    def test_create_bus_line_as_driver(self):
        """Test creating bus line as driver."""
        another_line = Line.objects.create(
            name='Line B',
            code='LB-01'
        )
        
        self.authenticate(self.driver_user)
        url = reverse('busline-list')
        data = {
            'bus': self.bus.pk,
            'line': another_line.pk
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_bus_line_tracking_status(self):
        """Test updating bus line tracking status."""
        self.authenticate(self.driver_user)
        url = reverse('busline-detail', kwargs={'pk': self.bus_line.pk})
        data = {
            'tracking_status': BUS_TRACKING_STATUS_ACTIVE,
            'start_time': timezone.now().isoformat()
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bus_line.refresh_from_db()
        self.assertEqual(self.bus_line.tracking_status, BUS_TRACKING_STATUS_ACTIVE)
    
    def test_filter_bus_lines_by_bus(self):
        """Test filtering bus lines by bus."""
        self.authenticate(self.passenger_user)
        url = reverse('busline-list')
        response = self.client.get(url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for bus_line in response.data['results']:
            self.assertEqual(bus_line['bus'], str(self.bus.pk))
    
    def test_filter_bus_lines_by_line(self):
        """Test filtering bus lines by line."""
        self.authenticate(self.passenger_user)
        url = reverse('busline-list')
        response = self.client.get(url, {'line': self.line.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for bus_line in response.data['results']:
            self.assertEqual(bus_line['line'], str(self.line.pk))


class LocationUpdateViewSetTestCase(TrackingAPITestCase):
    """Test cases for LocationUpdateViewSet."""
    
    def test_list_location_updates_unauthenticated(self):
        """Test listing location updates without authentication."""
        url = reverse('locationupdate-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_location_updates_as_passenger(self):
        """Test listing location updates as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('locationupdate-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_create_location_update_as_driver(self):
        """Test creating location update as driver."""
        self.authenticate(self.driver_user)
        url = reverse('locationupdate-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '36.7550',
            'longitude': '3.0450',
            'speed': '40.0',
            'heading': '90.0',
            'accuracy': '3.0',
            'line': self.line.pk,
            'nearest_stop': self.stop2.pk,
            'distance_to_stop': '100.0'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(LocationUpdate.objects.filter(
            bus=self.bus,
            latitude=Decimal('36.7550')
        ).exists())
    
    def test_create_location_update_as_passenger(self):
        """Test creating location update as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('locationupdate-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '36.7550',
            'longitude': '3.0450'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_location_update_with_trip_id(self):
        """Test creating location update with trip ID."""
        trip_id = uuid.uuid4()
        self.authenticate(self.driver_user)
        url = reverse('locationupdate-list')
        data = {
            'bus': self.bus.pk,
            'latitude': '36.7600',
            'longitude': '3.0500',
            'trip_id': str(trip_id),
            'line': self.line.pk
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        location = LocationUpdate.objects.get(trip_id=trip_id)
        self.assertEqual(location.trip_id, trip_id)
    
    def test_filter_location_updates_by_bus(self):
        """Test filtering location updates by bus."""
        self.authenticate(self.passenger_user)
        url = reverse('locationupdate-list')
        response = self.client.get(url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for location in response.data['results']:
            self.assertEqual(location['bus'], str(self.bus.pk))
    
    def test_filter_location_updates_by_line(self):
        """Test filtering location updates by line."""
        self.authenticate(self.passenger_user)
        url = reverse('locationupdate-list')
        response = self.client.get(url, {'line': self.line.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for location in response.data['results']:
            self.assertEqual(location['line'], str(self.line.pk))


class PassengerCountViewSetTestCase(TrackingAPITestCase):
    """Test cases for PassengerCountViewSet."""
    
    def test_list_passenger_counts_as_passenger(self):
        """Test listing passenger counts as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('passengercount-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_create_passenger_count_as_driver(self):
        """Test creating passenger count as driver."""
        self.authenticate(self.driver_user)
        url = reverse('passengercount-list')
        data = {
            'bus': self.bus.pk,
            'count': 18,
            'capacity': 25,
            'occupancy_rate': '0.72',
            'line': self.line.pk,
            'stop': self.stop2.pk
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PassengerCount.objects.filter(
            bus=self.bus,
            count=18
        ).exists())
    
    def test_create_passenger_count_invalid_occupancy(self):
        """Test creating passenger count with invalid occupancy rate."""
        self.authenticate(self.driver_user)
        url = reverse('passengercount-list')
        data = {
            'bus': self.bus.pk,
            'count': 30,  # More than capacity
            'capacity': 25,
            'occupancy_rate': '1.20'  # > 1.0
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_filter_passenger_counts_by_bus(self):
        """Test filtering passenger counts by bus."""
        self.authenticate(self.passenger_user)
        url = reverse('passengercount-list')
        response = self.client.get(url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for count in response.data['results']:
            self.assertEqual(count['bus'], str(self.bus.pk))


class WaitingPassengersViewSetTestCase(TrackingAPITestCase):
    """Test cases for WaitingPassengersViewSet."""
    
    def test_list_waiting_passengers(self):
        """Test listing waiting passengers."""
        self.authenticate(self.passenger_user)
        url = reverse('waitingpassengers-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_create_waiting_passengers_as_passenger(self):
        """Test creating waiting passengers report as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('waitingpassengers-list')
        data = {
            'stop': self.stop2.pk,
            'line': self.line.pk,
            'count': 12
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(WaitingPassengers.objects.filter(
            stop=self.stop2,
            count=12,
            reported_by=self.passenger_user
        ).exists())
    
    def test_create_waiting_passengers_without_line(self):
        """Test creating waiting passengers without specific line."""
        self.authenticate(self.passenger_user)
        url = reverse('waitingpassengers-list')
        data = {
            'stop': self.stop2.pk,
            'count': 5
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_filter_waiting_passengers_by_stop(self):
        """Test filtering waiting passengers by stop."""
        self.authenticate(self.passenger_user)
        url = reverse('waitingpassengers-list')
        response = self.client.get(url, {'stop': self.stop1.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for waiting in response.data['results']:
            self.assertEqual(waiting['stop'], str(self.stop1.pk))


class TripViewSetTestCase(TrackingAPITestCase):
    """Test cases for TripViewSet."""
    
    def test_list_trips_as_passenger(self):
        """Test listing trips as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('trip-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_create_trip_as_driver(self):
        """Test creating trip as driver."""
        self.authenticate(self.driver_user)
        url = reverse('trip-list')
        data = {
            'bus': self.bus.pk,
            'driver': self.driver.pk,
            'line': self.line.pk,
            'start_time': timezone.now().isoformat(),
            'start_stop': self.stop1.pk,
            'notes': 'Regular trip'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Trip.objects.filter(
            bus=self.bus,
            driver=self.driver,
            line=self.line
        ).count() >= 2)  # Original + new one
    
    def test_end_trip_as_driver(self):
        """Test ending trip as driver."""
        self.authenticate(self.driver_user)
        url = reverse('trip-detail', kwargs={'pk': self.trip.pk})
        data = {
            'end_time': timezone.now().isoformat(),
            'end_stop': self.stop2.pk,
            'is_completed': True,
            'distance': '15.2',
            'total_stops': 7
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertTrue(self.trip.is_completed)
        self.assertEqual(self.trip.total_stops, 7)
    
    def test_filter_trips_by_bus(self):
        """Test filtering trips by bus."""
        self.authenticate(self.passenger_user)
        url = reverse('trip-list')
        response = self.client.get(url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for trip in response.data['results']:
            self.assertEqual(trip['bus'], str(self.bus.pk))
    
    def test_filter_trips_by_driver(self):
        """Test filtering trips by driver."""
        self.authenticate(self.passenger_user)
        url = reverse('trip-list')
        response = self.client.get(url, {'driver': self.driver.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for trip in response.data['results']:
            self.assertEqual(trip['driver'], str(self.driver.pk))
    
    def test_filter_trips_by_completion(self):
        """Test filtering trips by completion status."""
        # Create completed trip
        completed_trip = Trip.objects.create(
            bus=self.bus,
            driver=self.driver,
            line=self.line,
            start_time=timezone.now(),
            end_time=timezone.now(),
            is_completed=True
        )
        
        self.authenticate(self.passenger_user)
        url = reverse('trip-list')
        
        # Filter completed trips
        response = self.client.get(url, {'is_completed': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for trip in response.data['results']:
            self.assertTrue(trip['is_completed'])
        
        # Filter ongoing trips
        response = self.client.get(url, {'is_completed': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for trip in response.data['results']:
            self.assertFalse(trip['is_completed'])


class AnomalyViewSetTestCase(TrackingAPITestCase):
    """Test cases for AnomalyViewSet."""
    
    def test_list_anomalies_as_admin(self):
        """Test listing anomalies as admin."""
        self.authenticate(self.admin_user)
        url = reverse('anomaly-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 1)
    
    def test_list_anomalies_as_passenger(self):
        """Test listing anomalies as passenger."""
        self.authenticate(self.passenger_user)
        url = reverse('anomaly-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_anomaly_as_admin(self):
        """Test creating anomaly as admin."""
        self.authenticate(self.admin_user)
        url = reverse('anomaly-list')
        data = {
            'bus': self.bus.pk,
            'trip': self.trip.pk,
            'type': 'route',
            'description': 'Bus deviated from route',
            'severity': 'high',
            'location_latitude': '36.7700',
            'location_longitude': '3.0600'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Anomaly.objects.filter(
            bus=self.bus,
            type='route'
        ).exists())
    
    def test_resolve_anomaly_as_admin(self):
        """Test resolving anomaly as admin."""
        self.authenticate(self.admin_user)
        url = reverse('anomaly-detail', kwargs={'pk': self.anomaly.pk})
        data = {
            'resolved': True,
            'resolved_at': timezone.now().isoformat(),
            'resolution_notes': 'Speed limit warning sent to driver'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.anomaly.refresh_from_db()
        self.assertTrue(self.anomaly.resolved)
        self.assertEqual(self.anomaly.resolution_notes, 'Speed limit warning sent to driver')
    
    def test_filter_anomalies_by_type(self):
        """Test filtering anomalies by type."""
        # Create different types of anomalies
        Anomaly.objects.create(
            bus=self.bus,
            type='schedule',
            description='Late departure',
            severity='low'
        )
        
        self.authenticate(self.admin_user)
        url = reverse('anomaly-list')
        
        # Filter by speed anomalies
        response = self.client.get(url, {'type': 'speed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for anomaly in response.data['results']:
            self.assertEqual(anomaly['type'], 'speed')
    
    def test_filter_anomalies_by_severity(self):
        """Test filtering anomalies by severity."""
        self.authenticate(self.admin_user)
        url = reverse('anomaly-list')
        response = self.client.get(url, {'severity': 'medium'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for anomaly in response.data['results']:
            self.assertEqual(anomaly['severity'], 'medium')
    
    def test_filter_anomalies_by_resolution(self):
        """Test filtering anomalies by resolution status."""
        self.authenticate(self.admin_user)
        url = reverse('anomaly-list')
        
        # Filter unresolved anomalies
        response = self.client.get(url, {'resolved': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for anomaly in response.data['results']:
            self.assertFalse(anomaly['resolved'])


class TrackingAPIIntegrationTestCase(TrackingAPITestCase):
    """Integration tests for tracking API."""
    
    def test_complete_tracking_flow(self):
        """Test complete bus tracking flow."""
        # Driver starts a trip
        self.authenticate(self.driver_user)
        
        # Create trip
        trip_url = reverse('trip-list')
        trip_data = {
            'bus': self.bus.pk,
            'driver': self.driver.pk,
            'line': self.line.pk,
            'start_time': timezone.now().isoformat(),
            'start_stop': self.stop1.pk
        }
        response = self.client.post(trip_url, trip_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        trip_id = response.data['id']
        
        # Update bus line tracking status
        bus_line_url = reverse('busline-detail', kwargs={'pk': self.bus_line.pk})
        response = self.client.patch(bus_line_url, {
            'tracking_status': BUS_TRACKING_STATUS_ACTIVE,
            'trip_id': trip_id,
            'start_time': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Send location updates during trip
        location_url = reverse('locationupdate-list')
        locations = [
            {'latitude': '36.7530', 'longitude': '3.0430', 'speed': '25.0'},
            {'latitude': '36.7550', 'longitude': '3.0450', 'speed': '35.0'},
            {'latitude': '36.7580', 'longitude': '3.0480', 'speed': '40.0'},
        ]
        
        for i, loc_data in enumerate(locations):
            loc_data.update({
                'bus': self.bus.pk,
                'line': self.line.pk,
                'trip_id': trip_id,
                'nearest_stop': self.stop1.pk if i < 2 else self.stop2.pk,
                'distance_to_stop': str(100 - i * 30)
            })
            response = self.client.post(location_url, loc_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Update passenger counts during trip
        passenger_count_url = reverse('passengercount-list')
        counts = [12, 18, 15]  # Passengers getting on/off
        
        for i, count in enumerate(counts):
            count_data = {
                'bus': self.bus.pk,
                'count': count,
                'capacity': 25,
                'occupancy_rate': str(count / 25),
                'line': self.line.pk,
                'stop': self.stop1.pk if i < 2 else self.stop2.pk,
                'trip_id': trip_id
            }
            response = self.client.post(passenger_count_url, count_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # End the trip
        trip_detail_url = reverse('trip-detail', kwargs={'pk': trip_id})
        end_data = {
            'end_time': timezone.now().isoformat(),
            'end_stop': self.stop2.pk,
            'is_completed': True,
            'distance': '5.2',
            'average_speed': '32.5',
            'max_passengers': 18,
            'total_stops': 2
        }
        response = self.client.patch(trip_detail_url, end_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Update bus line status to idle
        response = self.client.patch(bus_line_url, {
            'tracking_status': BUS_TRACKING_STATUS_IDLE,
            'end_time': timezone.now().isoformat()
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify passengers can see the trip data
        self.authenticate(self.passenger_user)
        
        # Check trip is visible
        response = self.client.get(trip_url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        trip_ids = [t['id'] for t in response.data['results']]
        self.assertIn(trip_id, trip_ids)
        
        # Check location updates are visible
        response = self.client.get(location_url, {'bus': self.bus.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    def test_passenger_reporting_flow(self):
        """Test passenger reporting flow."""
        self.authenticate(self.passenger_user)
        
        # Passenger reports waiting at stop
        waiting_url = reverse('waitingpassengers-list')
        waiting_data = {
            'stop': self.stop1.pk,
            'line': self.line.pk,
            'count': 6
        }
        response = self.client.post(waiting_url, waiting_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Another passenger reports at different stop
        waiting_data2 = {
            'stop': self.stop2.pk,
            'line': self.line.pk,
            'count': 4
        }
        response = self.client.post(waiting_url, waiting_data2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Driver can see waiting passengers
        self.authenticate(self.driver_user)
        response = self.client.get(waiting_url, {'line': self.line.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        total_waiting = sum(w['count'] for w in response.data['results'])
        self.assertGreater(total_waiting, 8)  # At least our reports + existing
        
        # Admin can see all reports
        self.authenticate(self.admin_user)
        response = self.client.get(waiting_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 3)
    
    def test_anomaly_detection_and_resolution_flow(self):
        """Test anomaly detection and resolution flow."""
        # Admin creates anomaly (simulating automatic detection)
        self.authenticate(self.admin_user)
        
        anomaly_url = reverse('anomaly-list')
        anomaly_data = {
            'bus': self.bus.pk,
            'trip': self.trip.pk,
            'type': 'bunching',
            'description': 'Two buses detected close together on same route',
            'severity': 'high',
            'location_latitude': '36.7600',
            'location_longitude': '3.0500'
        }
        response = self.client.post(anomaly_url, anomaly_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        anomaly_id = response.data['id']
        
        # Admin reviews and resolves anomaly
        anomaly_detail_url = reverse('anomaly-detail', kwargs={'pk': anomaly_id})
        resolution_data = {
            'resolved': True,
            'resolved_at': timezone.now().isoformat(),
            'resolution_notes': 'Dispatched one bus to different route'
        }
        response = self.client.patch(anomaly_detail_url, resolution_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify anomaly is resolved
        response = self.client.get(anomaly_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['resolved'])
        
        # Check resolved anomalies filter
        response = self.client.get(anomaly_url, {'resolved': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resolved_ids = [a['id'] for a in response.data['results']]
        self.assertIn(anomaly_id, resolved_ids)