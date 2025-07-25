# DZ Bus Tracker Fixtures

This directory contains fixture files with sample data for testing the DZ Bus Tracker application.

## 📁 Fixture Files

- **01_users.json** - User accounts and profiles (15 users: admins, drivers, passengers)
- **02_groups.json** - User groups and permissions
- **03_drivers.json** - Driver profiles and ratings
- **04_buses.json** - Buses and their current locations
- **05_lines.json** - Bus lines, stops, and schedules
- **06_tracking.json** - Real-time tracking data (trips, locations, passenger counts)
- **07_notifications.json** - Notifications and device tokens
- **all_essential_data.json** - Combined essential data for quick setup

## 🚀 Loading Fixtures

### Load All Fixtures (Recommended)
```bash
cd /path/to/dz_bus_tracker_v2
./load_fixtures.sh
```

### Load Essential Data Only
```bash
./load_essential_fixtures.sh
```

### Load Individual Fixtures
```bash
python manage.py loaddata fixtures/01_users.json
python manage.py loaddata fixtures/04_buses.json
# etc...
```

### Clear and Reload
```bash
# Clear database
python manage.py flush --no-input

# Reload all fixtures
./load_fixtures.sh
```

## 👥 Test Users

### Admins
- **Super Admin**: admin@dzbus.com / admin123
- **Manager**: manager@dzbus.com / manager123

### Drivers
- **Ahmed Benali**: ahmed.driver@dzbus.com / driver123 (Approved)
- **Mohamed Khaled**: mohamed.driver@dzbus.com / driver123 (Approved)
- **Youcef Amrani**: youcef.driver@dzbus.com / driver123 (Approved)
- **Karim Saidi**: karim.driver@dzbus.com / driver123 (Pending)
- **Rachid Belkacem**: rachid.driver@dzbus.com / driver123 (Pending)

### Passengers
- **Fatima Zahra**: fatima@dzbus.com / pass123
- **Ali Hassan**: ali@dzbus.com / pass123
- **Amina Bouzid**: amina@dzbus.com / pass123
- **Omar Tlemcani**: omar@dzbus.com / pass123
- **Sarah Meddah**: sarah@dzbus.com / pass123

## 📊 Sample Data Overview

- **5 Bus Lines**: L1-L5 covering different routes in Algiers
- **16 Bus Stops**: Major locations like Place des Martyrs, University, Airport
- **8 Buses**: 5 active, 3 in maintenance
- **5 Active Trips**: Currently running with GPS tracking
- **70 Schedules**: Different timings for weekdays and weekends
- **Driver Ratings**: Pre-populated for approved drivers
- **Notifications**: Sample notifications for testing

## 🧪 Testing with Fixtures

1. **Start Django Server**:
   ```bash
   python manage.py runserver
   ```

2. **Open Test Interface**:
   ```bash
   python serve_test_interface.py
   # Opens browser at http://localhost:8080
   ```

3. **Or Use API Documentation**:
   - Open http://localhost:8000/api/schema/swagger-ui/
   - Login with any test user
   - Test APIs interactively

## 📝 Notes

- All passwords are intentionally simple for testing (admin123, driver123, pass123)
- GPS coordinates are based on real Algiers locations
- Data relationships are properly maintained (drivers → buses → lines → trips)
- Fixtures use natural keys for better portability

## 🔄 Recreating Fixtures

If you modify the data and want to save new fixtures:

```bash
# Create new fixtures from current database
python create_fixtures.py

# This will overwrite existing fixture files
```