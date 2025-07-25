#!/usr/bin/env python3
"""
Create comprehensive sample data for DZ Bus Tracker.
This script creates various user types with simple passwords for testing.
"""

import os
import sys
import random
from datetime import datetime, timedelta

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, Profile
from apps.buses.models import Bus, BusLocation
from apps.drivers.models import Driver, DriverRating
from apps.lines.models import Line, Stop, Schedule, LineStop
from apps.tracking.models import BusLine, LocationUpdate, PassengerCount, Trip, WaitingPassengers, Anomaly
from apps.notifications.models import Notification, DeviceToken
from apps.core.constants import *
from apps.core.constants import (
    NOTIFICATION_TYPE_BUS_ARRIVING,
    NOTIFICATION_TYPE_BUS_DELAYED,
    NOTIFICATION_TYPE_SYSTEM,
)

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

class SampleDataCreator:
    def __init__(self):
        self.users = {}
        self.drivers = []
        self.buses = []
        self.lines = []
        self.stops = []
        
    def clean_existing_data(self):
        """Clean up existing test data."""
        info("Cleaning existing test data...")
        with transaction.atomic():
            # Delete test users (this will cascade delete related data)
            User.objects.filter(email__endswith='@dzbus.com').delete()
            User.objects.filter(email__endswith='@test.com').delete()
            
            # Clean up lines and stops
            Line.objects.filter(code__startswith='L').delete()
            Stop.objects.all().delete()
            
            # Clean up other data that might not cascade
            Bus.objects.all().delete()
            Driver.objects.all().delete()
            
            success("Existing test data cleaned")
    
    def create_users(self):
        """Create different types of users with simple passwords."""
        header("Creating Users")
        
        # Admin users
        info("Creating admin users...")
        self.users['super_admin'] = User.objects.create_superuser(
            email='admin@dzbus.com',
            password='admin123',
            first_name='Super',
            last_name='Admin',
            user_type=USER_TYPE_ADMIN
        )
        success("Created super admin: admin@dzbus.com (password: admin123)")
        
        self.users['manager'] = User.objects.create_user(
            email='manager@dzbus.com',
            password='manager123',
            first_name='Bus',
            last_name='Manager',
            user_type=USER_TYPE_ADMIN,
            is_staff=True
        )
        success("Created manager: manager@dzbus.com (password: manager123)")
        
        # Driver users
        info("Creating driver users...")
        driver_data = [
            ('Ahmed', 'Benali', 'ahmed.driver@dzbus.com', 'driver123'),
            ('Mohamed', 'Khaled', 'mohamed.driver@dzbus.com', 'driver123'),
            ('Youcef', 'Amrani', 'youcef.driver@dzbus.com', 'driver123'),
            ('Karim', 'Saidi', 'karim.driver@dzbus.com', 'driver123'),
            ('Rachid', 'Belkacem', 'rachid.driver@dzbus.com', 'driver123'),
        ]
        
        for first_name, last_name, email, password in driver_data:
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                user_type=USER_TYPE_DRIVER
            )
            self.users[f'driver_{first_name.lower()}'] = user
            success(f"Created driver: {email} (password: {password})")
        
        # Passenger users
        info("Creating passenger users...")
        passenger_data = [
            ('Fatima', 'Zahra', 'fatima@dzbus.com', 'pass123'),
            ('Ali', 'Hassan', 'ali@dzbus.com', 'pass123'),
            ('Amina', 'Bouzid', 'amina@dzbus.com', 'pass123'),
            ('Omar', 'Tlemcani', 'omar@dzbus.com', 'pass123'),
            ('Sarah', 'Meddah', 'sarah@dzbus.com', 'pass123'),
        ]
        
        for first_name, last_name, email, password in passenger_data:
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                user_type=USER_TYPE_PASSENGER
            )
            self.users[f'passenger_{first_name.lower()}'] = user
            success(f"Created passenger: {email} (password: {password})")
        
        success(f"Total users created: {len(self.users)}")
    
    def create_drivers(self):
        """Create driver profiles for driver users."""
        header("Creating Driver Profiles")
        
        driver_users = [u for u in self.users.values() if u.user_type == USER_TYPE_DRIVER]
        
        for i, user in enumerate(driver_users):
            driver = Driver.objects.create(
                user=user,
                phone_number=f'+21355512345{i}',
                id_card_number=f'1234567890{i}',
                driver_license_number=f'DL-2024-00{i+1}',
                years_of_experience=random.randint(2, 15),
                status=DRIVER_STATUS_APPROVED if i < 3 else DRIVER_STATUS_PENDING
            )
            self.drivers.append(driver)
            
            # Add ratings for approved drivers
            if driver.status == DRIVER_STATUS_APPROVED:
                # Get all passengers and randomly select some to rate this driver
                passengers = [u for u in self.users.values() if u.user_type == USER_TYPE_PASSENGER]
                num_ratings = min(len(passengers), random.randint(3, 5))
                rating_passengers = random.sample(passengers, num_ratings)
                
                for passenger in rating_passengers:
                    try:
                        DriverRating.objects.create(
                            driver=driver,
                            user=passenger,
                            rating=random.choice([3, 4, 4, 5, 5]),  # Mostly good ratings
                            comment=random.choice([
                                "Excellent driver, very professional",
                                "Good driving, safe and comfortable",
                                "Punctual and friendly",
                                "Safe driver",
                                ""
                            ])
                        )
                    except Exception:
                        # Skip if rating already exists for this user/driver/date combination
                        pass
            
            success(f"Created driver profile for {user.get_full_name()} - Status: {driver.get_status_display()}")
        
        success(f"Total driver profiles created: {len(self.drivers)}")
    
    def create_buses(self):
        """Create buses and assign to drivers."""
        header("Creating Buses")
        
        bus_models = [
            ('Mercedes-Benz', 'Sprinter 516 CDI', 2020, 30),
            ('Iveco', 'Daily 70C18', 2019, 35),
            ('Ford', 'Transit 430', 2021, 28),
            ('Peugeot', 'Boxer HDi', 2018, 25),
            ('Renault', 'Master dCi', 2020, 32),
            ('Hyundai', 'County', 2019, 29),
            ('Toyota', 'Coaster', 2021, 30),
            ('Isuzu', 'Journey', 2020, 33),
        ]
        
        approved_drivers = [d for d in self.drivers if d.status == DRIVER_STATUS_APPROVED]
        
        for i, (manufacturer, model, year, capacity) in enumerate(bus_models):
            driver = approved_drivers[i % len(approved_drivers)] if approved_drivers else None
            
            bus = Bus.objects.create(
                license_plate=f'16-{random.randint(100, 999)}-{random.randint(10, 99)}',
                driver=driver,
                model=model,
                manufacturer=manufacturer,
                year=year,
                capacity=capacity,
                status=BUS_STATUS_ACTIVE if i < 5 else BUS_STATUS_MAINTENANCE,
                is_air_conditioned=random.choice([True, False]),
                is_approved=True if i < 5 else False,
                features=['WiFi', 'USB Charging'] if random.choice([True, False]) else [],
                description=f"{manufacturer} {model} - Comfortable bus with {capacity} seats"
            )
            self.buses.append(bus)
            
            # Create current location for active buses
            if bus.status == BUS_STATUS_ACTIVE:
                BusLocation.objects.create(
                    bus=bus,
                    latitude=36.7528 + random.uniform(-0.05, 0.05),
                    longitude=3.0424 + random.uniform(-0.05, 0.05),
                    updated_at=timezone.now()
                )
            
            success(f"Created bus: {bus.license_plate} - {manufacturer} {model} ({year})")
        
        success(f"Total buses created: {len(self.buses)}")
    
    def create_lines_and_stops(self):
        """Create bus lines and stops."""
        header("Creating Lines and Stops")
        
        # Create stops across Algiers
        stop_data = [
            # Central area
            ('Place des Martyrs', 36.7810, 3.0600, 'Central square and major hub'),
            ('Grande Poste', 36.7753, 3.0588, 'Historic post office area'),
            ('Alger Centre', 36.7694, 3.0556, 'City center station'),
            ('Tafourah', 36.7734, 3.0512, 'Commercial district'),
            
            # University area
            ('Université d\'Alger', 36.7580, 3.0380, 'University campus main entrance'),
            ('Cité Universitaire', 36.7560, 3.0350, 'Student dormitories'),
            ('Faculté de Médecine', 36.7600, 3.0400, 'Medical school'),
            
            # Residential areas
            ('Bab El Oued', 36.7950, 3.0510, 'Residential neighborhood'),
            ('El Harrach', 36.7167, 3.1333, 'Eastern district'),
            ('Hussein Dey', 36.7389, 3.0956, 'Southeastern area'),
            ('Bir Mourad Raïs', 36.7370, 3.0520, 'Southern residential'),
            
            # Business areas
            ('Cheraga', 36.7670, 2.9590, 'Business district'),
            ('Dely Ibrahim', 36.7540, 2.9880, 'Commercial zone'),
            ('Ben Aknoun', 36.7580, 3.0140, 'Administrative area'),
            
            # Transport hubs
            ('Gare Routière', 36.7720, 3.0650, 'Main bus terminal'),
            ('Aéroport', 36.6914, 3.2153, 'Airport terminal'),
        ]
        
        for name, lat, lon, desc in stop_data:
            stop = Stop.objects.create(
                name=name,
                latitude=lat,
                longitude=lon,
                description=desc
            )
            self.stops.append(stop)
            success(f"Created stop: {name}")
        
        # Create lines
        line_data = [
            {
                'name': 'Line 1: Centre - University',
                'code': 'L1',
                'description': 'Main line connecting city center to university area',
                'color': '#FF0000',
                'stops': ['Alger Centre', 'Grande Poste', 'Tafourah', 'Ben Aknoun', 'Université d\'Alger', 'Cité Universitaire'],
            },
            {
                'name': 'Line 2: Bab El Oued - El Harrach',
                'code': 'L2',
                'description': 'East-West connection through the city',
                'color': '#00FF00',
                'stops': ['Bab El Oued', 'Place des Martyrs', 'Alger Centre', 'Hussein Dey', 'El Harrach'],
            },
            {
                'name': 'Line 3: Airport Express',
                'code': 'L3',
                'description': 'Direct connection to airport',
                'color': '#0000FF',
                'stops': ['Gare Routière', 'Alger Centre', 'Hussein Dey', 'Aéroport'],
            },
            {
                'name': 'Line 4: Business Route',
                'code': 'L4',
                'description': 'Connecting business districts',
                'color': '#FFA500',
                'stops': ['Cheraga', 'Dely Ibrahim', 'Ben Aknoun', 'Bir Mourad Raïs', 'Alger Centre'],
            },
            {
                'name': 'Line 5: University Circuit',
                'code': 'L5',
                'description': 'University campus circulation',
                'color': '#800080',
                'stops': ['Université d\'Alger', 'Faculté de Médecine', 'Cité Universitaire', 'Ben Aknoun'],
            },
        ]
        
        for line_info in line_data:
            line = Line.objects.create(
                name=line_info['name'],
                code=line_info['code'],
                description=line_info['description'],
                color=line_info['color'],
                is_active=True
            )
            
            # Add stops to line with order
            stop_names = line_info['stops']
            for order, stop_name in enumerate(stop_names):
                stop = Stop.objects.get(name=stop_name)
                LineStop.objects.create(
                    line=line,
                    stop=stop,
                    order=order,
                    average_time_from_previous=300 if order > 0 else 0  # 5 minutes in seconds
                )
            
            self.lines.append(line)
            success(f"Created line: {line.name} with {len(stop_names)} stops")
        
        # Create schedules for each line
        info("Creating schedules...")
        
        for line in self.lines:
            # Weekday schedule (Monday=0 to Friday=4)
            for day in range(5):
                Schedule.objects.create(
                    line=line,
                    day_of_week=day,
                    start_time='06:00:00',
                    end_time='22:00:00',
                    frequency_minutes=15 if line.code in ['L1', 'L2'] else 30
                )
            
            # Weekend schedule (Saturday=5, Sunday=6)
            for day in [5, 6]:
                Schedule.objects.create(
                    line=line,
                    day_of_week=day,
                    start_time='07:00:00',
                    end_time='21:00:00',
                    frequency_minutes=20 if line.code in ['L1', 'L2'] else 45
                )
        
        success("Created schedules for all lines")
    
    def create_active_operations(self):
        """Create active bus operations, trips, and tracking data."""
        header("Creating Active Operations")
        
        active_buses = [b for b in self.buses if b.status == BUS_STATUS_ACTIVE]
        
        for i, bus in enumerate(active_buses[:len(self.lines)]):
            line = self.lines[i]
            
            # Assign bus to line
            bus_line = BusLine.objects.create(
                bus=bus,
                line=line,
                tracking_status=BUS_TRACKING_STATUS_ACTIVE
            )
            success(f"Assigned bus {bus.license_plate} to {line.name}")
            
            # Create active trip
            stops = list(line.stops.all().order_by('line_stops__order'))
            if stops:
                trip = Trip.objects.create(
                    bus=bus,
                    driver=bus.driver,
                    line=line,
                    start_stop=stops[0],
                    end_stop=stops[-1],
                    start_time=timezone.now() - timedelta(minutes=random.randint(10, 30))
                )
                
                # Create location updates along the route
                for j in range(random.randint(3, 7)):
                    LocationUpdate.objects.create(
                        bus=bus,
                        latitude=36.7528 + random.uniform(-0.05, 0.05),
                        longitude=3.0424 + random.uniform(-0.05, 0.05),
                        speed=random.uniform(20, 50),
                        heading=random.uniform(0, 360),
                        accuracy=random.uniform(5, 15),
                        line=line,
                        nearest_stop=random.choice(stops),
                        distance_to_stop=random.uniform(50, 500)
                    )
                
                # Create passenger count
                passenger_count = random.randint(10, bus.capacity - 5)
                PassengerCount.objects.create(
                    bus=bus,
                    count=passenger_count,
                    capacity=bus.capacity,
                    occupancy_rate=passenger_count / bus.capacity,
                    trip_id=trip.id
                )
                
                # Create waiting passengers at stops
                for stop in random.sample(stops, min(3, len(stops))):
                    WaitingPassengers.objects.create(
                        stop=stop,
                        line=line,
                        count=random.randint(5, 20),
                        reported_by=random.choice([u for u in self.users.values() if u.user_type == USER_TYPE_PASSENGER])
                    )
                
                success(f"Created active trip for bus {bus.license_plate} on {line.name}")
    
    def create_notifications(self):
        """Create sample notifications and device tokens."""
        header("Creating Notifications")
        
        # Create device tokens for some users
        info("Creating device tokens...")
        for user in random.sample(list(self.users.values()), min(8, len(self.users))):
            DeviceToken.objects.create(
                user=user,
                token=f"sample_token_{user.id}_{random.randint(1000, 9999)}",
                device_type=random.choice(['ios', 'android']),
                is_active=True
            )
        
        # Create notifications
        notification_templates = [
            {
                'title': 'Bus Arriving Soon',
                'message': 'Bus {bus_number} will arrive at {stop_name} in approximately 5 minutes',
                'notification_type': NOTIFICATION_TYPE_BUS_ARRIVING
            },
            {
                'title': 'Route Delay Alert',
                'message': 'Line {line_name} is experiencing delays due to traffic',
                'notification_type': NOTIFICATION_TYPE_BUS_DELAYED
            },
            {
                'title': 'Service Update',
                'message': 'New schedule effective from tomorrow for Line {line_name}',
                'notification_type': NOTIFICATION_TYPE_SYSTEM
            },
        ]
        
        for template in notification_templates:
            # Create for random passengers
            for user in random.sample([u for u in self.users.values() if u.user_type == USER_TYPE_PASSENGER], 3):
                Notification.objects.create(
                    user=user,
                    title=template['title'],
                    message=template['message'].format(
                        bus_number=random.choice(self.buses).license_plate,
                        stop_name=random.choice(self.stops).name,
                        line_name=random.choice(self.lines).name
                    ),
                    notification_type=template['notification_type'],
                    is_read=random.choice([True, False])
                )
        
        success("Created sample notifications")
    
    def print_summary(self):
        """Print summary of created data."""
        header("Sample Data Creation Summary")
        
        print(f"{GREEN}Users Created:{RESET}")
        print(f"  • Super Admin: 1")
        print(f"  • Managers: 1")
        print(f"  • Drivers: {User.objects.filter(user_type=USER_TYPE_DRIVER).count()}")
        print(f"  • Passengers: {User.objects.filter(user_type=USER_TYPE_PASSENGER).count()}")
        print(f"  • Total: {User.objects.count()}")
        
        print(f"\n{GREEN}Operations Data:{RESET}")
        print(f"  • Driver Profiles: {Driver.objects.count()}")
        print(f"  • Buses: {Bus.objects.count()}")
        print(f"  • Lines: {Line.objects.count()}")
        print(f"  • Stops: {Stop.objects.count()}")
        print(f"  • Active Trips: {Trip.objects.filter(end_time__isnull=True).count()}")
        print(f"  • Location Updates: {LocationUpdate.objects.count()}")
        
        print(f"\n{GREEN}Login Credentials:{RESET}")
        print(f"  • Admin: admin@dzbus.com / admin123")
        print(f"  • Manager: manager@dzbus.com / manager123")
        print(f"  • Driver: ahmed.driver@dzbus.com / driver123")
        print(f"  • Passenger: fatima@dzbus.com / pass123")
        
        print(f"\n{GREEN}API Endpoints:{RESET}")
        print(f"  • Admin Panel: http://localhost:8000/admin/")
        print(f"  • API Documentation: http://localhost:8000/api/schema/swagger-ui/")
        print(f"  • API Root: http://localhost:8000/api/v1/")
        print(f"  • Token Auth: http://localhost:8000/api/token/")
    
    def run(self):
        """Run the complete sample data creation process."""
        try:
            self.clean_existing_data()
            self.create_users()
            self.create_drivers()
            self.create_buses()
            self.create_lines_and_stops()
            self.create_active_operations()
            self.create_notifications()
            self.print_summary()
            
            print(f"\n{GREEN}✓ Sample data creation completed successfully!{RESET}")
            
        except Exception as e:
            error(f"Error creating sample data: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    creator = SampleDataCreator()
    creator.run()