#!/usr/bin/env python3
"""
Create fixtures from existing sample data.
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.core.management import call_command
from django.contrib.auth.models import Group
from apps.accounts.models import User
from apps.buses.models import Bus
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop
from apps.tracking.models import LocationUpdate, Trip, WaitingPassengers
from apps.notifications.models import Notification

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def create_fixture(app_label, model_names, filename, indent=2):
    """Create a fixture file for specified models."""
    print(f"{YELLOW}Creating fixture: {filename}{RESET}")
    
    # Build the model list
    models = [f"{app_label}.{model}" for model in model_names]
    
    # Use dumpdata to create the fixture
    with open(f"fixtures/{filename}", 'w') as f:
        call_command(
            'dumpdata',
            *models,
            format='json',
            indent=indent,
            stdout=f,
            natural_foreign=True,
            natural_primary=True
        )
    
    print(f"{GREEN}✓ Created {filename}{RESET}")

def main():
    print(f"{BLUE}Creating fixtures for DZ Bus Tracker{RESET}\n")
    
    # Create fixtures for each app
    fixtures = [
        # Users and authentication
        {
            'app': 'accounts',
            'models': ['User', 'Profile'],
            'filename': '01_users.json',
            'description': 'Users and profiles'
        },
        # Auth groups (if any)
        {
            'app': 'auth',
            'models': ['Group'],
            'filename': '02_groups.json',
            'description': 'User groups'
        },
        # Drivers
        {
            'app': 'drivers',
            'models': ['Driver', 'DriverRating'],
            'filename': '03_drivers.json',
            'description': 'Drivers and ratings'
        },
        # Buses
        {
            'app': 'buses',
            'models': ['Bus', 'BusLocation'],
            'filename': '04_buses.json',
            'description': 'Buses and locations'
        },
        # Lines and stops
        {
            'app': 'lines',
            'models': ['Stop', 'Line', 'LineStop', 'Schedule'],
            'filename': '05_lines.json',
            'description': 'Lines, stops, and schedules'
        },
        # Tracking data
        {
            'app': 'tracking',
            'models': ['BusLine', 'LocationUpdate', 'PassengerCount', 'Trip', 'WaitingPassengers'],
            'filename': '06_tracking.json',
            'description': 'Tracking and trip data'
        },
        # Notifications
        {
            'app': 'notifications',
            'models': ['Notification', 'DeviceToken'],
            'filename': '07_notifications.json',
            'description': 'Notifications and device tokens'
        },
    ]
    
    # Create each fixture
    for fixture in fixtures:
        print(f"\n{fixture['description']}:")
        create_fixture(
            fixture['app'],
            fixture['models'],
            fixture['filename']
        )
    
    # Create a combined fixture with essential data
    print(f"\n{YELLOW}Creating combined fixture...{RESET}")
    essential_models = [
        'accounts.User',
        'accounts.Profile',
        'drivers.Driver',
        'buses.Bus',
        'lines.Stop',
        'lines.Line',
        'lines.LineStop',
        'lines.Schedule',
        'tracking.BusLine',
        'tracking.Trip',
    ]
    
    with open('fixtures/all_essential_data.json', 'w') as f:
        call_command(
            'dumpdata',
            *essential_models,
            format='json',
            indent=2,
            stdout=f,
            natural_foreign=True,
            natural_primary=True
        )
    print(f"{GREEN}✓ Created all_essential_data.json{RESET}")
    
    # Create loading script
    print(f"\n{YELLOW}Creating fixture loading script...{RESET}")
    
    load_script = """#!/bin/bash
# Load fixtures for DZ Bus Tracker

echo "Loading DZ Bus Tracker fixtures..."

# Load in order of dependencies
echo "Loading users..."
python manage.py loaddata fixtures/01_users.json

echo "Loading groups..."
python manage.py loaddata fixtures/02_groups.json

echo "Loading drivers..."
python manage.py loaddata fixtures/03_drivers.json

echo "Loading buses..."
python manage.py loaddata fixtures/04_buses.json

echo "Loading lines and stops..."
python manage.py loaddata fixtures/05_lines.json

echo "Loading tracking data..."
python manage.py loaddata fixtures/06_tracking.json

echo "Loading notifications..."
python manage.py loaddata fixtures/07_notifications.json

echo "✓ All fixtures loaded successfully!"
"""
    
    with open('load_fixtures.sh', 'w') as f:
        f.write(load_script)
    
    os.chmod('load_fixtures.sh', 0o755)
    print(f"{GREEN}✓ Created load_fixtures.sh{RESET}")
    
    # Create a quick load script for essential data only
    quick_load_script = """#!/bin/bash
# Quick load essential fixtures only

echo "Loading essential DZ Bus Tracker data..."
python manage.py loaddata fixtures/all_essential_data.json
echo "✓ Essential data loaded successfully!"
"""
    
    with open('load_essential_fixtures.sh', 'w') as f:
        f.write(quick_load_script)
    
    os.chmod('load_essential_fixtures.sh', 0o755)
    print(f"{GREEN}✓ Created load_essential_fixtures.sh{RESET}")
    
    # Print summary
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Fixtures created successfully!{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")
    
    print(f"\n{GREEN}To load all fixtures:{RESET}")
    print("  ./load_fixtures.sh")
    
    print(f"\n{GREEN}To load only essential data:{RESET}")
    print("  ./load_essential_fixtures.sh")
    
    print(f"\n{GREEN}To load individual fixtures:{RESET}")
    print("  python manage.py loaddata fixtures/01_users.json")
    print("  python manage.py loaddata fixtures/03_drivers.json")
    print("  # etc...")
    
    print(f"\n{GREEN}User credentials in fixtures:{RESET}")
    print("  • Admin: admin@dzbus.com / admin123")
    print("  • Manager: manager@dzbus.com / manager123")
    print("  • Driver: ahmed.driver@dzbus.com / driver123")
    print("  • Passenger: fatima@dzbus.com / pass123")

if __name__ == '__main__':
    main()