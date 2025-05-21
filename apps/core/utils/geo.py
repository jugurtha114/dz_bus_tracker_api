"""
Geographic utilities for DZ Bus Tracker.
"""
import math
from datetime import datetime, timedelta

from django.conf import settings
from geopy.distance import geodesic
import logging

logger = logging.getLogger(__name__)


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points in kilometers.

    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point

    Returns:
        Distance in kilometers
    """
    try:
        point1 = (float(lat1), float(lon1))
        point2 = (float(lat2), float(lon2))
        return geodesic(point1, point2).kilometers
    except Exception as e:
        logger.error(f"Error calculating distance: {e}")
        return None


def calculate_speed(lat1, lon1, time1, lat2, lon2, time2):
    """
    Calculate speed between two location updates in km/h.

    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        time1: Timestamp of first point
        lat2: Latitude of second point
        lon2: Longitude of second point
        time2: Timestamp of second point

    Returns:
        Speed in kilometers per hour
    """
    try:
        # Calculate distance
        distance_km = calculate_distance(lat1, lon1, lat2, lon2)
        if distance_km is None:
            return None

        # Calculate time difference in hours
        time_diff = (time2 - time1).total_seconds() / 3600

        # Avoid division by zero
        if time_diff <= 0:
            return 0

        # Calculate speed
        speed = distance_km / time_diff

        # Sanity check - cap at reasonable maximum speed for a bus (120 km/h)
        if speed > 120:
            logger.warning(f"Calculated speed {speed} km/h seems unreasonably high")
            return 120

        return speed
    except Exception as e:
        logger.error(f"Error calculating speed: {e}")
        return None


def calculate_eta(current_lat, current_lon, destination_lat, destination_lon, current_speed,
                  historical_travel_time=None, traffic_factor=1.0):
    """
    Calculate estimated time of arrival (ETA) to a destination.

    Args:
        current_lat: Current latitude
        current_lon: Current longitude
        destination_lat: Destination latitude
        destination_lon: Destination longitude
        current_speed: Current speed in km/h
        historical_travel_time: Optional historical travel time in seconds
        traffic_factor: Traffic factor adjustment (1.0 = normal traffic)

    Returns:
        ETA as a datetime object
    """
    try:
        # Calculate remaining distance
        distance_km = calculate_distance(
            current_lat, current_lon, destination_lat, destination_lon
        )

        if distance_km is None:
            return None

        # Use historical data if available and speed is reasonable
        if historical_travel_time and (current_speed is None or current_speed < 5):
            # Adjust historical time based on remaining distance
            adjusted_time_seconds = historical_travel_time * traffic_factor
            eta = datetime.now() + timedelta(seconds=adjusted_time_seconds)
            logger.debug(f"ETA calculated using historical data: {eta}")
            return eta

        # Calculate based on current speed
        if current_speed and current_speed > 0:
            time_hours = distance_km / current_speed
            time_seconds = time_hours * 3600

            # Apply traffic factor
            adjusted_time_seconds = time_seconds * traffic_factor

            eta = datetime.now() + timedelta(seconds=adjusted_time_seconds)
            logger.debug(f"ETA calculated using current speed: {eta}")
            return eta

        # Fallback: use average bus speed of 25 km/h in urban areas
        avg_speed = 25.0
        time_hours = distance_km / avg_speed
        time_seconds = time_hours * 3600

        # Apply traffic factor
        adjusted_time_seconds = time_seconds * traffic_factor

        eta = datetime.now() + timedelta(seconds=adjusted_time_seconds)
        logger.debug(f"ETA calculated using average speed: {eta}")
        return eta

    except Exception as e:
        logger.error(f"Error calculating ETA: {e}")
        return None


def get_traffic_factor(hour_of_day, day_of_week):
    """
    Get traffic factor based on time of day and day of week.

    Args:
        hour_of_day: Hour of day (0-23)
        day_of_week: Day of week (0-6, where 0 is Monday)

    Returns:
        Traffic factor as a float, where 1.0 means normal traffic
    """
    # Define peak hours (higher values mean more traffic/slower travel)
    weekday_peaks = {
        7: 1.5,  # Morning rush hour (7-8 AM)
        8: 1.6,
        16: 1.4,  # Evening rush hour (4-7 PM)
        17: 1.5,
        18: 1.3,
    }

    weekend_peaks = {
        11: 1.2,  # Weekend peaks (11 AM - 1 PM, 5-7 PM)
        12: 1.3,
        17: 1.2,
        18: 1.2,
    }

    # Check if it's a weekend (5=Saturday, 6=Sunday)
    is_weekend = day_of_week >= 5

    # Get traffic factor
    if is_weekend:
        return weekend_peaks.get(hour_of_day, 1.0)
    else:
        return weekday_peaks.get(hour_of_day, 1.0)


def is_location_in_algeria(latitude, longitude):
    """
    Check if a location is within Algeria's boundaries.

    Args:
        latitude: Latitude
        longitude: Longitude

    Returns:
        Boolean indicating if location is in Algeria
    """
    # Approximate bounding box for Algeria
    min_lat, max_lat = 19.0, 37.5
    min_lon, max_lon = -8.7, 12.0

    try:
        lat = float(latitude)
        lon = float(longitude)

        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
    except Exception as e:
        logger.error(f"Error checking location: {e}")
        return False


def decode_google_polyline(polyline_str):
    """
    Decode a polyline string into a list of (latitude, longitude) tuples.

    Args:
        polyline_str: Encoded polyline string

    Returns:
        List of (lat, lng) tuples
    """
    points = []
    index = 0
    lat = 0
    lng = 0

    while index < len(polyline_str):
        result = 1
        shift = 0

        # Extract latitude
        while True:
            b = ord(polyline_str[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break

        lat += (~(result >> 1) if (result & 1) else (result >> 1))

        # Extract longitude
        result = 1
        shift = 0

        while True:
            b = ord(polyline_str[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break

        lng += (~(result >> 1) if (result & 1) else (result >> 1))

        points.append((lat * 1e-5, lng * 1e-5))

    return points