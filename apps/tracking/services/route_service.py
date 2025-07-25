"""
Route and path estimation services for real-time tracking.
"""
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from apps.core.exceptions import ValidationError
from apps.tracking.models import LocationUpdate, Trip, RouteSegment
from apps.lines.models import Stop, LineStop
from apps.buses.models import Bus


class RouteService:
    """Service for route calculation and path estimation."""
    
    @classmethod
    def get_estimated_route(cls, bus_id: str, destination_stop_id: Optional[str] = None) -> Dict:
        """
        Get the estimated route for a bus including future path.
        
        Args:
            bus_id: Bus ID
            destination_stop_id: Optional specific destination stop
            
        Returns:
            Dict containing route information and estimations
        """
        try:
            bus = Bus.objects.get(id=bus_id)
            
            # Get current location
            latest_location = LocationUpdate.objects.filter(
                bus=bus
            ).order_by('-created_at').first()
            
            if not latest_location:
                raise ValidationError("No location data available for this bus")
            
            # Get active trip and line
            active_trip = Trip.objects.filter(
                bus=bus,
                end_time__isnull=True
            ).first()
            
            if not active_trip:
                return {
                    'current_location': {
                        'latitude': latest_location.latitude,
                        'longitude': latest_location.longitude,
                        'timestamp': latest_location.created_at
                    },
                    'status': 'idle',
                    'message': 'Bus is not on an active trip'
                }
            
            # Get remaining stops
            remaining_stops = cls._get_remaining_stops(
                active_trip.line,
                latest_location.latitude,
                latest_location.longitude,
                destination_stop_id
            )
            
            # Calculate estimated path
            estimated_path = cls._calculate_estimated_path(
                latest_location,
                remaining_stops,
                bus.average_speed or 30.0  # Default 30 km/h
            )
            
            # Get historical data for better estimation
            historical_data = cls._get_historical_travel_times(
                active_trip.line_id,
                remaining_stops
            )
            
            return {
                'bus_id': str(bus.id),
                'bus_number': bus.bus_number,
                'driver': {
                    'id': str(bus.driver.id) if bus.driver else None,
                    'name': bus.driver.user.get_full_name() if bus.driver else None
                },
                'current_location': {
                    'latitude': latest_location.latitude,
                    'longitude': latest_location.longitude,
                    'speed': latest_location.speed,
                    'heading': latest_location.heading,
                    'timestamp': latest_location.created_at,
                    'accuracy': latest_location.accuracy
                },
                'trip': {
                    'id': str(active_trip.id),
                    'line': active_trip.line.name,
                    'started_at': active_trip.start_time,
                    'progress': cls._calculate_trip_progress(active_trip, latest_location)
                },
                'estimated_path': estimated_path,
                'remaining_stops': remaining_stops,
                'historical_data': historical_data,
                'traffic_conditions': cls._get_traffic_conditions(
                    float(latest_location.latitude),
                    float(latest_location.longitude)
                )
            }
            
        except Bus.DoesNotExist:
            raise ValidationError(f"Bus with ID {bus_id} not found")
    
    @classmethod
    def get_arrival_estimates(cls, stop_id: str, line_id: Optional[str] = None) -> List[Dict]:
        """
        Get arrival estimates for all buses approaching a stop.
        
        Args:
            stop_id: Stop ID
            line_id: Optional line ID to filter by
            
        Returns:
            List of arrival estimates
        """
        try:
            stop = Stop.objects.get(id=stop_id)
            
            # Get all active trips passing through this stop
            query = Trip.objects.filter(
                end_time__isnull=True,
                line__stops=stop
            )
            
            if line_id:
                query = query.filter(line_id=line_id)
            
            estimates = []
            
            for trip in query:
                # Get bus current location
                latest_location = LocationUpdate.objects.filter(
                    bus=trip.bus
                ).order_by('-created_at').first()
                
                if not latest_location:
                    continue
                
                # Check if bus has already passed this stop
                if cls._has_passed_stop(trip, stop):
                    continue
                
                # Calculate ETA
                eta_data = cls._calculate_eta_to_stop(
                    trip.bus,
                    latest_location,
                    stop,
                    trip.line
                )
                
                if eta_data:
                    estimates.append({
                        'bus': {
                            'id': str(trip.bus.id),
                            'number': trip.bus.bus_number,
                            'capacity': trip.bus.capacity,
                            'current_passengers': trip.bus.current_passenger_count
                        },
                        'driver': {
                            'id': str(trip.bus.driver.id) if trip.bus.driver else None,
                            'name': trip.bus.driver.user.get_full_name() if trip.bus.driver else None,
                            'rating': trip.bus.driver.rating if trip.bus.driver else None
                        },
                        'line': {
                            'id': str(trip.line.id),
                            'name': trip.line.name,
                            'color': trip.line.color
                        },
                        'current_location': {
                            'latitude': latest_location.latitude,
                            'longitude': latest_location.longitude,
                            'distance_to_stop': eta_data['distance']
                        },
                        'eta': eta_data['eta'],
                        'eta_minutes': eta_data['eta_minutes'],
                        'reliability': eta_data['reliability'],
                        'last_update': latest_location.created_at
                    })
            
            # Sort by ETA
            estimates.sort(key=lambda x: x['eta'])
            
            return estimates
            
        except Stop.DoesNotExist:
            raise ValidationError(f"Stop with ID {stop_id} not found")
    
    @classmethod
    def get_route_visualization_data(cls, line_id: str) -> Dict:
        """
        Get route data optimized for map visualization.
        
        Args:
            line_id: Line ID
            
        Returns:
            Dict with route polylines and markers
        """
        cache_key = f"route_visualization_{line_id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            from apps.lines.models import Line
            line = Line.objects.get(id=line_id)
            
            # Get ordered stops
            stops = line.stops.through.objects.filter(
                line=line
            ).order_by('order').select_related('stop')
            
            # Build route segments
            route_segments = []
            markers = []
            
            for i, line_stop in enumerate(stops):
                stop = line_stop.stop
                
                # Add stop marker
                markers.append({
                    'id': str(stop.id),
                    'name': stop.name,
                    'position': {
                        'lat': float(stop.latitude),
                        'lng': float(stop.longitude)
                    },
                    'type': 'stop',
                    'order': i + 1,
                    'is_terminal': i == 0 or i == len(stops) - 1
                })
                
                # Get route to next stop
                if i < len(stops) - 1:
                    next_stop = stops[i + 1].stop
                    
                    # Try to get route from Google Maps or stored segments
                    segment = cls._get_route_segment(stop, next_stop)
                    if segment:
                        route_segments.append(segment)
            
            # Get active buses on this line
            active_buses = cls._get_active_buses_on_line(line)
            
            visualization_data = {
                'line': {
                    'id': str(line.id),
                    'name': line.name,
                    'color': line.color,
                    'total_stops': len(stops)
                },
                'route': {
                    'segments': route_segments,
                    'total_distance': sum(s.get('distance', 0) for s in route_segments if s.get('distance') is not None),
                    'estimated_duration': sum(s.get('duration', 0) for s in route_segments if s.get('duration') is not None)
                },
                'markers': markers,
                'active_buses': active_buses,
                'bounds': cls._calculate_bounds(markers),
                'last_updated': timezone.now()
            }
            
            # Cache for 5 minutes
            cache.set(cache_key, visualization_data, 300)
            
            return visualization_data
            
        except Line.DoesNotExist:
            raise ValidationError(f"Line with ID {line_id} not found")
    
    @classmethod
    def _get_remaining_stops(cls, line, current_lat: float, current_lng: float, 
                           destination_stop_id: Optional[str] = None) -> List[Dict]:
        """Get remaining stops on the route."""
        # Find closest stop to current position
        stops = line.stops.through.objects.filter(
            line=line
        ).order_by('order').select_related('stop')
        
        closest_stop_index = 0
        min_distance = float('inf')
        
        for i, line_stop in enumerate(stops):
            stop = line_stop.stop
            distance = cls._calculate_distance(
                current_lat, current_lng,
                float(stop.latitude), float(stop.longitude)
            )
            
            if distance < min_distance:
                min_distance = distance
                closest_stop_index = i
        
        # Get remaining stops
        remaining = []
        for line_stop in stops[closest_stop_index:]:
            stop = line_stop.stop
            stop_data = {
                'id': str(stop.id),
                'name': stop.name,
                'location': {
                    'lat': float(stop.latitude),
                    'lng': float(stop.longitude)
                },
                'order': line_stop.order,
                'estimated_arrival': None  # Will be calculated
            }
            
            remaining.append(stop_data)
            
            if destination_stop_id and str(stop.id) == destination_stop_id:
                break
        
        return remaining
    
    @classmethod
    def _calculate_estimated_path(cls, current_location, remaining_stops, 
                                average_speed: float) -> List[Dict]:
        """Calculate the estimated path with time estimates."""
        path = []
        current_time = timezone.now()
        current_lat = float(current_location.latitude)
        current_lng = float(current_location.longitude)
        
        for stop in remaining_stops:
            # Calculate distance and time to stop
            distance = cls._calculate_distance(
                current_lat, current_lng,
                stop['location']['lat'], stop['location']['lng']
            )
            
            # Estimate time (distance in km, speed in km/h)
            travel_time_hours = distance / average_speed
            travel_time_minutes = int(travel_time_hours * 60)
            
            arrival_time = current_time + timedelta(minutes=travel_time_minutes)
            
            stop['estimated_arrival'] = arrival_time
            stop['distance_km'] = round(distance, 2)
            stop['travel_time_minutes'] = travel_time_minutes
            
            # Add path segment
            path.append({
                'from': {
                    'lat': current_lat,
                    'lng': current_lng
                },
                'to': stop['location'],
                'distance': distance,
                'estimated_duration': travel_time_minutes,
                'estimated_arrival': arrival_time
            })
            
            # Update current position for next iteration
            current_lat = stop['location']['lat']
            current_lng = stop['location']['lng']
            current_time = arrival_time
        
        return path
    
    @classmethod
    def _calculate_distance(cls, lat1: float, lng1: float, 
                          lat2: float, lng2: float) -> float:
        """Calculate distance between two points in kilometers."""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lng = radians(lng2 - lng1)
        
        a = sin(delta_lat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    @classmethod
    def _get_traffic_conditions(cls, lat: float, lng: float) -> Dict:
        """Get current traffic conditions (placeholder for real implementation)."""
        # This would integrate with Google Maps Traffic API
        return {
            'level': 'moderate',
            'factor': 1.2,  # Traffic multiplier for time estimates
            'description': 'Moderate traffic conditions'
        }
    
    @classmethod
    def _calculate_trip_progress(cls, trip, current_location) -> float:
        """Calculate trip progress percentage."""
        # Get all stops
        total_stops = trip.line.stops.count()
        
        # Find closest stop index
        stops = trip.line.stops.through.objects.filter(
            line=trip.line
        ).order_by('order').select_related('stop')
        
        closest_index = 0
        min_distance = float('inf')
        
        for i, line_stop in enumerate(stops):
            stop = line_stop.stop
            distance = cls._calculate_distance(
                float(current_location.latitude), float(current_location.longitude),
                float(stop.latitude), float(stop.longitude)
            )
            
            if distance < min_distance:
                min_distance = distance
                closest_index = i
        
        # Calculate progress
        progress = (closest_index / max(total_stops - 1, 1)) * 100
        return round(progress, 2)
    
    @classmethod
    def _get_route_segment(cls, from_stop: Stop, to_stop: Stop) -> Optional[Dict]:
        """Get route segment between two stops."""
        # Check if we have stored route
        segment = RouteSegment.objects.filter(
            from_stop=from_stop,
            to_stop=to_stop
        ).first()
        
        if segment and segment.polyline:
            return {
                'from_stop_id': str(from_stop.id),
                'to_stop_id': str(to_stop.id),
                'polyline': segment.polyline,
                'distance': segment.distance,
                'duration': segment.duration
            }
        
        # Otherwise return straight line
        return {
            'from_stop_id': str(from_stop.id),
            'to_stop_id': str(to_stop.id),
            'polyline': None,  # Will draw straight line
            'distance': cls._calculate_distance(
                float(from_stop.latitude), float(from_stop.longitude),
                float(to_stop.latitude), float(to_stop.longitude)
            ),
            'duration': None
        }
    
    @classmethod
    def _get_active_buses_on_line(cls, line) -> List[Dict]:
        """Get all active buses on a line."""
        active_buses = []
        
        trips = Trip.objects.filter(
            line=line,
            end_time__isnull=True
        ).select_related('bus', 'bus__driver')
        
        for trip in trips:
            latest_location = LocationUpdate.objects.filter(
                bus=trip.bus
            ).order_by('-created_at').first()
            
            if latest_location:
                active_buses.append({
                    'id': str(trip.bus.id),
                    'number': trip.bus.bus_number,
                    'position': {
                        'lat': float(latest_location.latitude),
                        'lng': float(latest_location.longitude)
                    },
                    'heading': latest_location.heading,
                    'speed': latest_location.speed,
                    'driver': trip.bus.driver.user.get_full_name() if trip.bus.driver else None,
                    'last_update': latest_location.created_at,
                    'passenger_count': trip.bus.current_passenger_count
                })
        
        return active_buses
    
    @classmethod
    def _calculate_bounds(cls, markers: List[Dict]) -> Dict:
        """Calculate map bounds for markers."""
        if not markers:
            return None
        
        lats = [m['position']['lat'] for m in markers]
        lngs = [m['position']['lng'] for m in markers]
        
        return {
            'north': max(lats),
            'south': min(lats),
            'east': max(lngs),
            'west': min(lngs)
        }
    
    @classmethod
    def _has_passed_stop(cls, trip: Trip, stop: Stop) -> bool:
        """Check if bus has already passed a stop."""
        # This would check trip history or location updates
        # For now, return False
        return False
    
    @classmethod
    def _calculate_eta_to_stop(cls, bus: Bus, current_location, 
                             stop: Stop, line) -> Optional[Dict]:
        """Calculate ETA to a specific stop."""
        distance = cls._calculate_distance(
            float(current_location.latitude), float(current_location.longitude),
            float(stop.latitude), float(stop.longitude)
        )
        
        # Use current speed or average
        speed = float(current_location.speed) if current_location.speed and float(current_location.speed) > 0 else 30.0
        
        # Calculate time
        travel_time_hours = distance / speed
        travel_time_minutes = int(travel_time_hours * 60)
        
        eta = timezone.now() + timedelta(minutes=travel_time_minutes)
        
        # Calculate reliability based on data freshness
        from django.utils import timezone as tz
        data_age = (tz.now() - current_location.created_at).seconds
        reliability = max(0, 100 - (data_age / 60))  # Decrease by 1% per minute
        
        return {
            'eta': eta,
            'eta_minutes': travel_time_minutes,
            'distance': round(distance, 2),
            'reliability': round(reliability, 2)
        }
    
    @classmethod
    def _get_historical_travel_times(cls, line_id: str, 
                                   stops: List[Dict]) -> Dict:
        """Get historical travel time data."""
        # This would query historical trip data
        # For now, return empty
        return {
            'average_times': {},
            'peak_times': {},
            'off_peak_times': {}
        }