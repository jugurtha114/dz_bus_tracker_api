# DZ Bus Tracker - User Testing Guide

## 🚀 Quick Start

### Loading Sample Data

```bash
# Option 1: Load all fixtures (recommended for full testing)
./load_fixtures.sh

# Option 2: Load only essential data (faster)
./load_essential_fixtures.sh

# Option 3: Fresh start with sample data
python create_sample_data.py
```

## 👥 User Accounts & Testing Scenarios

### 1. Super Admin Account
**Email:** admin@dzbus.com  
**Password:** admin123

#### What you can do:
- Access Django Admin Panel at http://localhost:8000/admin/
- View and manage all users, drivers, buses, and routes
- Approve/reject driver applications
- Create and modify bus schedules
- View system-wide statistics
- Access all API endpoints with full permissions

#### Test scenarios:
```bash
# Login to admin panel
# Navigate to http://localhost:8000/admin/
# Use credentials above

# API Test - Get all users (admin only)
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@dzbus.com","password":"admin123"}' \
  | python -m json.tool

# Use the access token for authenticated requests
TOKEN="your-access-token-here"

curl -X GET http://localhost:8000/api/v1/accounts/users/ \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Manager Account
**Email:** manager@dzbus.com  
**Password:** manager123

#### What you can do:
- Manage bus operations
- View driver performance reports
- Monitor real-time bus tracking
- Handle passenger complaints
- View operational statistics

#### Test scenarios:
```bash
# Get auth token
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@dzbus.com","password":"manager123"}'

# View all active buses
curl -X GET http://localhost:8000/api/v1/buses/ \
  -H "Authorization: Bearer $TOKEN"

# View driver list with ratings
curl -X GET http://localhost:8000/api/v1/drivers/ \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Driver Accounts

#### Approved Drivers:
- **Ahmed Benali:** ahmed.driver@dzbus.com / driver123
- **Mohamed Khaled:** mohamed.driver@dzbus.com / driver123
- **Youcef Amrani:** youcef.driver@dzbus.com / driver123

#### Pending Approval:
- **Karim Saidi:** karim.driver@dzbus.com / driver123
- **Rachid Belkacem:** rachid.driver@dzbus.com / driver123

#### What drivers can do:
- View assigned bus and route
- Start/end trips
- Update bus location
- Report passenger count
- View their ratings and feedback
- Update availability status

#### Test scenarios:
```bash
# Login as driver
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"ahmed.driver@dzbus.com","password":"driver123"}'

# Get driver profile
curl -X GET http://localhost:8000/api/v1/drivers/profile/ \
  -H "Authorization: Bearer $TOKEN"

# Update bus location (if assigned to a bus)
curl -X POST http://localhost:8000/api/v1/tracking/locations/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 36.7538,
    "longitude": 3.0588,
    "speed": 35.5,
    "heading": 180
  }'

# Update passenger count
curl -X POST http://localhost:8000/api/v1/tracking/passenger-count/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "count": 25
  }'
```

### 4. Passenger Accounts
- **Fatima Zahra:** fatima@dzbus.com / pass123
- **Ali Hassan:** ali@dzbus.com / pass123
- **Amina Bouzid:** amina@dzbus.com / pass123
- **Omar Tlemcani:** omar@dzbus.com / pass123
- **Sarah Meddah:** sarah@dzbus.com / pass123

#### What passengers can do:
- View bus routes and schedules
- Track buses in real-time
- See estimated arrival times
- Report waiting at stops
- Rate drivers
- Receive notifications
- View nearby stops

#### Test scenarios:
```bash
# Login as passenger
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"fatima@dzbus.com","password":"pass123"}'

# View all bus lines
curl -X GET http://localhost:8000/api/v1/lines/ \
  -H "Authorization: Bearer $TOKEN"

# View real-time bus locations
curl -X GET http://localhost:8000/api/v1/tracking/locations/ \
  -H "Authorization: Bearer $TOKEN"

# Get buses near a location
curl -X GET "http://localhost:8000/api/v1/tracking/locations/?latitude=36.7538&longitude=3.0588&radius=1000" \
  -H "Authorization: Bearer $TOKEN"

# Report waiting at a stop
curl -X POST http://localhost:8000/api/v1/tracking/waiting-passengers/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "stop": "stop-id-here",
    "line": "line-id-here",
    "count": 5
  }'

# Rate a driver
curl -X POST http://localhost:8000/api/v1/drivers/ratings/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "driver": "driver-id-here",
    "rating": 5,
    "comment": "Excellent service!"
  }'
```

## 📱 API Testing with Swagger UI

1. Open http://localhost:8000/api/schema/swagger-ui/
2. Click "Authorize" button
3. Use the `/api/token/` endpoint to get a JWT token
4. Enter the token in the format: `Bearer your-token-here`
5. Now you can test all endpoints interactively

## 🗺️ Sample Data Overview

### Bus Lines
1. **L1: Centre - University** - Main line connecting city center to university
2. **L2: Bab El Oued - El Harrach** - East-West connection
3. **L3: Airport Express** - Direct airport connection
4. **L4: Business Route** - Connecting business districts
5. **L5: University Circuit** - Campus circulation

### Active Buses (with real-time tracking)
- 5 buses currently active on different lines
- 3 buses in maintenance
- All active buses have GPS tracking enabled

### Bus Stops
16 stops across Algiers including:
- Place des Martyrs
- Grande Poste
- Université d'Alger
- Aéroport
- And more...

## 🧪 Testing Different Scenarios

### Scenario 1: Morning Commute (Passenger)
1. Login as a passenger
2. Check bus schedules for your route
3. View real-time location of buses
4. Report waiting at your stop
5. Track the bus as it approaches

### Scenario 2: Driver Shift (Driver)
1. Login as an approved driver
2. View your assigned bus and route
3. Start a trip
4. Update location periodically
5. Update passenger count at stops
6. End trip

### Scenario 3: Operations Management (Manager)
1. Login as manager
2. View all active buses on map
3. Check driver performance metrics
4. Review passenger feedback
5. Handle any reported issues

### Scenario 4: System Administration (Admin)
1. Login as admin
2. Approve pending driver applications
3. Add new bus to fleet
4. Create new route
5. View system analytics

## 🔧 Resetting Data

```bash
# Clear all data
python manage.py flush --no-input

# Reload fixtures
./load_fixtures.sh

# Or create fresh sample data
python create_sample_data.py
```

## 📝 Notes

- All passwords are set to simple values for testing (e.g., "admin123", "driver123", "pass123")
- The sample data includes realistic Algiers locations and Arabic/French names
- GPS coordinates are based on actual Algiers geography
- Bus schedules differ between weekdays and weekends
- Driver ratings are pre-populated for approved drivers

## 🚨 Troubleshooting

If you encounter issues:

1. **Authentication errors**: Make sure you're using the correct email/password
2. **Permission denied**: Check if your user type has access to that endpoint
3. **Server not running**: Start with `python manage.py runserver`
4. **Database errors**: Run migrations with `python manage.py migrate`

Happy testing! 🚌