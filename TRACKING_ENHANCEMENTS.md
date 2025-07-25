# DZ Bus Tracker - Enhanced Tracking Features

## Overview

The DZ Bus Tracker now includes advanced real-time tracking capabilities with estimated paths, arrival times, and Google Maps integration.

## New Features

### 1. Real-time Driver Tracking with Estimated Paths

**API Endpoint**: `GET /api/v1/tracking/routes/bus_route/`

Get the estimated route for a specific bus including:
- Current location with speed and heading
- Remaining stops with ETAs
- Estimated path segments
- Trip progress percentage
- Traffic conditions
- Historical travel time data

**Parameters**:
- `bus_id` (required): UUID of the bus
- `destination_stop_id` (optional): Specific destination stop

**Example Response**:
```json
{
  "bus_id": "123e4567-e89b-12d3-a456-426614174000",
  "bus_number": "16136351",
  "driver": {
    "id": "driver-uuid",
    "name": "Ahmed Benali"
  },
  "current_location": {
    "latitude": 36.7538,
    "longitude": 3.0588,
    "speed": 35.5,
    "heading": 180,
    "timestamp": "2025-07-24T10:30:00Z",
    "accuracy": 5.0
  },
  "trip": {
    "id": "trip-uuid",
    "line": "Line 1: Centre - University",
    "started_at": "2025-07-24T10:00:00Z",
    "progress": 45.5
  },
  "estimated_path": [
    {
      "from": {"lat": 36.7538, "lng": 3.0588},
      "to": {"lat": 36.7520, "lng": 3.0570},
      "distance": 2.5,
      "estimated_duration": 5,
      "estimated_arrival": "2025-07-24T10:35:00Z"
    }
  ],
  "remaining_stops": [
    {
      "id": "stop-uuid",
      "name": "Place des Martyrs",
      "location": {"lat": 36.7520, "lng": 3.0570},
      "order": 3,
      "estimated_arrival": "2025-07-24T10:35:00Z",
      "distance_km": 2.5,
      "travel_time_minutes": 5
    }
  ],
  "traffic_conditions": {
    "level": "moderate",
    "factor": 1.2,
    "description": "Moderate traffic conditions"
  }
}
```

### 2. Estimated Arrival Times for Passengers

**API Endpoint**: `GET /api/v1/tracking/routes/arrivals/`

Get arrival estimates for all buses approaching a specific stop.

**Parameters**:
- `stop_id` (required): UUID of the stop
- `line_id` (optional): Filter by specific line

**Example Response**:
```json
[
  {
    "bus": {
      "id": "bus-uuid",
      "number": "16136351",
      "capacity": 50,
      "current_passengers": 23
    },
    "driver": {
      "id": "driver-uuid",
      "name": "Ahmed Benali",
      "rating": 4.5
    },
    "line": {
      "id": "line-uuid",
      "name": "Line 1: Centre - University",
      "color": "#FF0000"
    },
    "current_location": {
      "latitude": 36.7538,
      "longitude": 3.0588,
      "distance_to_stop": 2.5
    },
    "eta": "2025-07-24T10:35:00Z",
    "eta_minutes": 5,
    "reliability": 85.5,
    "last_update": "2025-07-24T10:30:00Z"
  }
]
```

### 3. Route Visualization Data

**API Endpoint**: `GET /api/v1/tracking/routes/visualization/`

Get route data optimized for map visualization.

**Parameters**:
- `line_id` (required): UUID of the line

**Example Response**:
```json
{
  "line": {
    "id": "line-uuid",
    "name": "Line 1: Centre - University",
    "color": "#FF0000",
    "total_stops": 15
  },
  "route": {
    "segments": [
      {
        "from_stop_id": "stop1-uuid",
        "to_stop_id": "stop2-uuid",
        "polyline": "encoded_polyline_string",
        "distance": 2.5,
        "duration": 5
      }
    ],
    "total_distance": 25.5,
    "estimated_duration": 45
  },
  "markers": [
    {
      "id": "stop-uuid",
      "name": "Alger Centre",
      "position": {"lat": 36.7538, "lng": 3.0588},
      "type": "stop",
      "order": 1,
      "is_terminal": true
    }
  ],
  "active_buses": [
    {
      "id": "bus-uuid",
      "number": "16136351",
      "position": {"lat": 36.7530, "lng": 3.0580},
      "heading": 180,
      "speed": 35.5,
      "driver": "Ahmed Benali",
      "last_update": "2025-07-24T10:30:00Z",
      "passenger_count": 23
    }
  ],
  "bounds": {
    "north": 36.7600,
    "south": 36.7400,
    "east": 3.0700,
    "west": 3.0400
  }
}
```

### 4. Driver Self-Tracking

**API Endpoint**: `GET /api/v1/tracking/routes/track_me/`

Drivers can track their own bus location and route.

**Authentication**: Requires authenticated driver user

**Response**: Same format as bus_route endpoint

### 5. Google Maps Integration

A complete HTML template is provided at `/templates/tracking_map.html` that includes:

- Real-time bus tracking on Google Maps
- Line and stop visualization
- Approaching buses for selected stops
- Driver controls for location updates
- Auto-refresh every 30 seconds
- Mobile-responsive design

**Features**:
- Interactive map with custom markers
- Route polylines with line colors
- Real-time bus positions with heading indicators
- Stop markers with ETA information
- User location tracking
- Driver-specific controls

**Usage**:
1. Replace `YOUR_API_KEY` with your Google Maps API key
2. Ensure users are authenticated (access token in localStorage)
3. Serve the template through Django views

### 6. Route Segments

**API Endpoint**: `/api/v1/tracking/route-segments/`

Manage stored route segments between stops for accurate path visualization.

**Model**: `RouteSegment`
- Stores polyline data between stops
- Includes distance and duration estimates
- Supports Google Maps encoded polylines

## Data Models

### RouteSegment

New model for storing route information:

```python
class RouteSegment(BaseModel):
    from_stop = ForeignKey(Stop)
    to_stop = ForeignKey(Stop)
    polyline = TextField()  # Encoded polyline
    distance = FloatField()  # Distance in km
    duration = IntegerField()  # Duration in minutes
```

### Bus Model Updates

Added fields to Bus model:
- `average_speed`: Default 30 km/h for ETA calculations
- `bus_number`: Property for simplified license plate
- `current_passenger_count`: Property for latest passenger count

## Implementation Details

### Route Service

The `RouteService` class provides methods for:
- `get_estimated_route()`: Calculate estimated route and ETAs
- `get_arrival_estimates()`: Get buses approaching a stop
- `get_route_visualization_data()`: Prepare data for map display
- Distance calculations using Haversine formula
- Traffic condition integration (placeholder for real API)
- Historical travel time analysis

### Caching

Route visualization data is cached for 5 minutes to improve performance.

### Real-time Updates

- Location updates trigger cache refreshes
- WebSocket support can be added for push notifications
- Polling recommended at 30-second intervals

## Testing

Test the endpoints with sample data:

```bash
# Get bus route
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/tracking/routes/bus_route/?bus_id=BUS_UUID"

# Get arrival estimates
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/tracking/routes/arrivals/?stop_id=STOP_UUID"

# Get visualization data
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/tracking/routes/visualization/?line_id=LINE_UUID"
```

## Future Enhancements

1. **Google Maps Directions API Integration**
   - Real-time traffic data
   - Accurate route polylines
   - Alternative route suggestions

2. **Push Notifications**
   - WebSocket support for real-time updates
   - Mobile push notifications for approaching buses

3. **Machine Learning**
   - Arrival time prediction based on historical data
   - Traffic pattern analysis
   - Passenger demand forecasting

4. **Offline Support**
   - Cache route data for offline access
   - Queue location updates when offline

5. **Advanced Analytics**
   - Heat maps of passenger density
   - Route optimization suggestions
   - Driver performance metrics