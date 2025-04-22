import math
from typing import Tuple, Dict, Any

from geopy.distance import geodesic


def calculate_distance(
    point1: Tuple[float, float], 
    point2: Tuple[float, float]
) -> float:
    """
    Calculate distance between two geographic points in meters.
    
    Args:
        point1: (latitude, longitude) of first point
        point2: (latitude, longitude) of second point
        
    Returns:
        Distance in meters
    """
    return geodesic(point1, point2).meters


def calculate_bearing(
    point1: Tuple[float, float], 
    point2: Tuple[float, float]
) -> float:
    """
    Calculate the bearing between two points in degrees.
    
    Args:
        point1: (latitude, longitude) of first point
        point2: (latitude, longitude) of second point
        
    Returns:
        Bearing in degrees (0-360)
    """
    lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
    lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])
    
    delta_lon = lon2 - lon1
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    bearing = math.atan2(x, y)
    
    # Convert to degrees
    bearing = math.degrees(bearing)
    
    # Normalize to 0-360
    bearing = (bearing + 360) % 360
    
    return bearing


def estimate_time(
    distance: float, 
    avg_speed: float = 20.0
) -> int:
    """
    Estimate travel time based on distance and average speed.
    
    Args:
        distance: Distance in meters
        avg_speed: Average speed in km/h (default: 20 km/h for urban bus)
        
    Returns:
        Estimated time in seconds
    """
    # Convert distance to km and speed to m/s
    distance_km = distance / 1000
    speed_ms = avg_speed / 3.6
    
    # Calculate time in seconds
    return int(distance_km * 3600 / avg_speed)


def calculate_location_from_bearing(
    start_point: Tuple[float, float], 
    bearing: float, 
    distance: float
) -> Tuple[float, float]:
    """
    Calculate a new location point given a starting point, bearing and distance.
    
    Args:
        start_point: (latitude, longitude) of starting point
        bearing: Bearing in degrees
        distance: Distance in meters
        
    Returns:
        (latitude, longitude) of the new point
    """
    # Convert to radians
    lat1 = math.radians(start_point[0])
    lon1 = math.radians(start_point[1])
    bearing_rad = math.radians(bearing)
    
    # Earth radius in meters
    R = 6371000
    
    # Calculate new position
    dist_rad = distance / R
    
    lat2 = math.asin(
        math.sin(lat1) * math.cos(dist_rad) + 
        math.cos(lat1) * math.sin(dist_rad) * math.cos(bearing_rad)
    )
    
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(dist_rad) * math.cos(lat1),
        math.cos(dist_rad) - math.sin(lat1) * math.sin(lat2)
    )
    
    # Convert back to degrees
    lat2 = math.degrees(lat2)
    lon2 = math.degrees(lon2)
    
    return (lat2, lon2)


def point_to_dict(point: Tuple[float, float]) -> Dict[str, float]:
    """
    Convert a point tuple to a dictionary.
    
    Args:
        point: (latitude, longitude) tuple
        
    Returns:
        Dictionary with 'latitude' and 'longitude' keys
    """
    return {"latitude": point[0], "longitude": point[1]}


def dict_to_point(point_dict: Dict[str, Any]) -> Tuple[float, float]:
    """
    Convert a point dictionary to a tuple.
    
    Args:
        point_dict: Dictionary with 'latitude' and 'longitude' keys
        
    Returns:
        (latitude, longitude) tuple
    """
    return (float(point_dict["latitude"]), float(point_dict["longitude"]))


def is_point_near_line(
    point: Tuple[float, float],
    line_start: Tuple[float, float],
    line_end: Tuple[float, float],
    threshold_meters: float = 50.0
) -> bool:
    """
    Check if a point is near a line segment within a threshold distance.
    
    Args:
        point: (latitude, longitude) of the point to check
        line_start: (latitude, longitude) of the line start
        line_end: (latitude, longitude) of the line end
        threshold_meters: Maximum distance in meters
        
    Returns:
        True if the point is within the threshold distance of the line
    """
    # Calculate distances
    d_point_to_start = calculate_distance(point, line_start)
    d_point_to_end = calculate_distance(point, line_end)
    d_start_to_end = calculate_distance(line_start, line_end)
    
    # If the line is very short, just check distance to either end
    if d_start_to_end < 1:
        return min(d_point_to_start, d_point_to_end) <= threshold_meters
    
    # Calculate the semi-perimeter
    s = (d_point_to_start + d_point_to_end + d_start_to_end) / 2
    
    # Calculate the area of the triangle
    area = math.sqrt(s * (s - d_point_to_start) * (s - d_point_to_end) * (s - d_start_to_end))
    
    # Calculate the height of the triangle (perpendicular distance)
    height = 2 * area / d_start_to_end
    
    # Check if the point is near the line segment
    return height <= threshold_meters and d_point_to_start + d_point_to_end <= d_start_to_end + threshold_meters * 2
