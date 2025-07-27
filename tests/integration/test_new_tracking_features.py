#!/usr/bin/env python3
"""
Test the new tracking features and API endpoints.
"""

import os
import sys
import django
import json
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import LocationUpdate, Trip, RouteSegment
from apps.tracking.services.route_service import RouteService

User = get_user_model()

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

def header(msg):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{msg.center(60)}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

class TrackingFeatureTester:
    def __init__(self):
        self.client = APIClient()
        self.driver = None
        self.bus = None
        self.line = None
        self.trip = None
        
    def setup_test_data(self):
        """Setup test data for tracking features."""
        header("Setting Up Test Data")
        
        # Get a driver with active bus
        self.driver = Driver.objects.filter(
            status='approved',
            buses__status='active'
        ).first()
        
        if not self.driver:
            error("No approved driver with active bus found")
            return False
            
        self.bus = self.driver.buses.filter(status='active').first()
        info(f"Using driver: {self.driver.user.get_full_name()}")
        info(f"Using bus: {self.bus.license_plate}")
        
        # Get or create an active trip
        self.trip = Trip.objects.filter(
            bus=self.bus,
            end_time__isnull=True
        ).first()
        
        if not self.trip:
            # Create a trip
            self.line = Line.objects.first()
            if self.line:
                self.trip = Trip.objects.create(
                    bus=self.bus,
                    driver=self.driver,
                    line=self.line,
                    start_time=timezone.now()
                )
                success(f"Created trip on line: {self.line.name}")
        else:
            self.line = self.trip.line
            info(f"Using existing trip on line: {self.line.name}")
        
        # Create some location updates
        locations = [
            (36.7538, 3.0588, 30.0),  # Alger Centre
            (36.7530, 3.0580, 35.5),  # Moving south
            (36.7520, 3.0570, 40.0),  # Approaching next stop
        ]
        
        for i, (lat, lng, speed) in enumerate(locations):
            LocationUpdate.objects.create(
                bus=self.bus,
                latitude=lat,
                longitude=lng,
                speed=speed,
                heading=180,
                accuracy=5.0,
                trip_id=self.trip.id if self.trip else None,
                line=self.line
            )
            
        success("Created location updates")
        
        # Authenticate as driver
        self.client.force_authenticate(user=self.driver.user)
        
        return True
    
    def test_bus_route_endpoint(self):
        """Test the bus route estimation endpoint."""
        header("Testing Bus Route Endpoint")
        
        response = self.client.get(f'/api/v1/tracking/routes/bus_route/?bus_id={self.bus.id}')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            # Verify response structure
            required_fields = ['bus_id', 'current_location', 'estimated_path', 'remaining_stops']
            for field in required_fields:
                if field in data:
                    success(f"Field '{field}' present")
                else:
                    error(f"Field '{field}' missing")
            
            # Display some data
            if 'current_location' in data:
                loc = data['current_location']
                info(f"Current location: ({loc.get('latitude')}, {loc.get('longitude')})")
                info(f"Speed: {loc.get('speed')} km/h")
            
            if 'remaining_stops' in data:
                info(f"Remaining stops: {len(data['remaining_stops'])}")
                for stop in data['remaining_stops'][:3]:
                    info(f"  - {stop.get('name')} (ETA: {stop.get('travel_time_minutes')} min)")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_arrivals_endpoint(self):
        """Test the arrivals estimation endpoint."""
        header("Testing Arrivals Endpoint")
        
        # Get a stop from the line
        stop = self.line.stops.first() if self.line else Stop.objects.first()
        
        if not stop:
            error("No stops found")
            return False
        
        info(f"Testing arrivals at stop: {stop.name}")
        
        response = self.client.get(f'/api/v1/tracking/routes/arrivals/?stop_id={stop.id}')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if isinstance(data, list):
                info(f"Found {len(data)} approaching buses")
                
                for bus_info in data[:3]:
                    if 'bus' in bus_info and 'eta_minutes' in bus_info:
                        success(f"Bus {bus_info['bus'].get('number')} - ETA: {bus_info['eta_minutes']} minutes")
                    
                    # Check reliability
                    if 'reliability' in bus_info:
                        info(f"  Reliability: {bus_info['reliability']}%")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_visualization_endpoint(self):
        """Test the route visualization endpoint."""
        header("Testing Route Visualization Endpoint")
        
        if not self.line:
            error("No line available for testing")
            return False
        
        response = self.client.get(f'/api/v1/tracking/routes/visualization/?line_id={self.line.id}')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            # Verify response structure
            if 'line' in data:
                success(f"Line: {data['line'].get('name')}")
                info(f"Total stops: {data['line'].get('total_stops')}")
            
            if 'route' in data:
                route = data['route']
                info(f"Route segments: {len(route.get('segments', []))}")
                info(f"Total distance: {route.get('total_distance')} km")
            
            if 'markers' in data:
                info(f"Map markers: {len(data['markers'])}")
            
            if 'active_buses' in data:
                info(f"Active buses on line: {len(data['active_buses'])}")
                for bus in data['active_buses'][:3]:
                    info(f"  - Bus {bus.get('number')} (Speed: {bus.get('speed')} km/h)")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_track_me_endpoint(self):
        """Test the driver self-tracking endpoint."""
        header("Testing Track Me Endpoint")
        
        response = self.client.get('/api/v1/tracking/routes/track_me/')
        
        if response.status_code == 200:
            success(f"Status: {response.status_code}")
            data = response.data
            
            if 'bus_id' in data and str(data['bus_id']) == str(self.bus.id):
                success("Correct bus returned for driver")
            
            if 'driver' in data:
                driver_info = data['driver']
                info(f"Driver: {driver_info.get('name')}")
            
            if 'trip' in data and data['trip']:
                trip_info = data['trip']
                info(f"Current trip: {trip_info.get('line')}")
                info(f"Progress: {trip_info.get('progress')}%")
            
            return True
        else:
            error(f"Status: {response.status_code}")
            error(f"Response: {response.data}")
            return False
    
    def test_route_segments(self):
        """Test route segments endpoint."""
        header("Testing Route Segments")
        
        # Create a test route segment
        if self.line and self.line.stops.count() >= 2:
            stops = list(self.line.stops.all()[:2])
            
            # Check if segment already exists
            from apps.tracking.models import RouteSegment
            existing = RouteSegment.objects.filter(
                from_stop=stops[0],
                to_stop=stops[1]
            ).first()
            
            if existing:
                success(f"Route segment already exists: {existing}")
                # Test retrieval
                response = self.client.get('/api/v1/tracking/route-segments/')
                if response.status_code == 200:
                    success(f"Retrieved {len(response.data.get('results', []))} route segments")
                    return True
            
            # Create route segment
            segment_data = {
                'from_stop': stops[0].id,
                'to_stop': stops[1].id,
                'polyline': 'test_polyline_encoded_string',
                'distance': 2.5,
                'duration': 5
            }
            
            response = self.client.post('/api/v1/tracking/route-segments/', segment_data, format='json')
            
            if response.status_code == 201:
                success("Created route segment")
                
                # Test retrieval
                response = self.client.get('/api/v1/tracking/route-segments/')
                if response.status_code == 200:
                    success(f"Retrieved {len(response.data.get('results', []))} route segments")
                    return True
            else:
                error(f"Failed to create route segment: {response.data}")
        else:
            info("Not enough stops to test route segments")
        
        return False
    
    def test_passenger_access(self):
        """Test endpoints with passenger access."""
        header("Testing Passenger Access")
        
        # Get a passenger user
        passenger = User.objects.filter(user_type='passenger').first()
        if not passenger:
            error("No passenger user found")
            return False
        
        self.client.force_authenticate(user=passenger)
        info(f"Testing as passenger: {passenger.email}")
        
        # Test arrivals (should work)
        stop = Stop.objects.first()
        response = self.client.get(f'/api/v1/tracking/routes/arrivals/?stop_id={stop.id}')
        
        if response.status_code == 200:
            success("Passenger can check arrivals")
        else:
            error(f"Passenger cannot check arrivals: {response.status_code}")
        
        # Test visualization (should work)
        response = self.client.get(f'/api/v1/tracking/routes/visualization/?line_id={self.line.id}')
        
        if response.status_code == 200:
            success("Passenger can view route visualization")
        else:
            error(f"Passenger cannot view visualization: {response.status_code}")
        
        # Test track_me (should fail - drivers only)
        response = self.client.get('/api/v1/tracking/routes/track_me/')
        
        if response.status_code == 403:
            success("Passenger correctly denied from track_me endpoint")
        else:
            error(f"Unexpected status for passenger track_me: {response.status_code}")
        
        return True
    
    def run_all_tests(self):
        """Run all tracking feature tests."""
        print(f"\n{BLUE}DZ Bus Tracker - New Tracking Features Test{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}\n")
        
        if not self.setup_test_data():
            error("Failed to setup test data")
            return
        
        tests_passed = 0
        tests_total = 6
        
        # Run tests
        if self.test_bus_route_endpoint():
            tests_passed += 1
        
        if self.test_arrivals_endpoint():
            tests_passed += 1
        
        if self.test_visualization_endpoint():
            tests_passed += 1
        
        if self.test_track_me_endpoint():
            tests_passed += 1
        
        if self.test_route_segments():
            tests_passed += 1
        
        if self.test_passenger_access():
            tests_passed += 1
        
        # Summary
        header("Test Summary")
        print(f"Tests passed: {tests_passed}/{tests_total}")
        
        if tests_passed == tests_total:
            success("All tests passed!")
        else:
            error(f"{tests_total - tests_passed} tests failed")

if __name__ == '__main__':
    tester = TrackingFeatureTester()
    tester.run_all_tests()