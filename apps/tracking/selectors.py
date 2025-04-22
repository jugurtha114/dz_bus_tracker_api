from django.db.models import Prefetch, Q, Count
from django.utils import timezone
from django.core.cache import cache

from apps.core.constants import CACHE_KEY_LOCATION
from utils.cache import cached_result
from .models import TrackingSession, LocationUpdate, TrackingLog, OfflineLocationBatch


def get_tracking_session_by_id(session_id):
    """
    Get a tracking session by ID.
    
    Args:
        session_id: ID of the session to retrieve
        
    Returns:
        TrackingSession instance or None
    """
    try:
        return TrackingSession.objects.select_related(
            'driver', 'bus', 'line', 'schedule'
        ).get(id=session_id)
    except TrackingSession.DoesNotExist:
        return None


@cached_result('active_sessions', timeout=60)
def get_active_tracking_sessions():
    """
    Get all active tracking sessions.
    
    Returns:
        Queryset of active tracking sessions
    """
    return TrackingSession.objects.filter(
        status='active',
        is_active=True,
    ).select_related(
        'driver', 'bus', 'line', 'schedule'
    )


def get_active_sessions_for_line(line_id):
    """
    Get active tracking sessions for a line.
    
    Args:
        line_id: ID of the line
        
    Returns:
        Queryset of active tracking sessions for the line
    """
    return TrackingSession.objects.filter(
        line_id=line_id,
        status='active',
        is_active=True,
    ).select_related(
        'driver', 'bus', 'line', 'schedule'
    )


def get_active_sessions_for_bus(bus_id):
    """
    Get active tracking sessions for a bus.
    
    Args:
        bus_id: ID of the bus
        
    Returns:
        Queryset of active tracking sessions for the bus
    """
    return TrackingSession.objects.filter(
        bus_id=bus_id,
        status='active',
        is_active=True,
    ).select_related(
        'driver', 'bus', 'line', 'schedule'
    )


def get_active_sessions_for_driver(driver_id):
    """
    Get active tracking sessions for a driver.
    
    Args:
        driver_id: ID of the driver
        
    Returns:
        Queryset of active tracking sessions for the driver
    """
    return TrackingSession.objects.filter(
        driver_id=driver_id,
        status='active',
        is_active=True,
    ).select_related(
        'driver', 'bus', 'line', 'schedule'
    )


def get_location_updates_for_session(session_id, start_time=None, end_time=None, limit=None):
    """
    Get location updates for a tracking session.
    
    Args:
        session_id: ID of the session
        start_time: Optional start time filter
        end_time: Optional end time filter
        limit: Optional limit on the number of results
        
    Returns:
        Queryset of location updates
    """
    queryset = LocationUpdate.objects.filter(session_id=session_id)
    
    if start_time:
        queryset = queryset.filter(timestamp__gte=start_time)
    
    if end_time:
        queryset = queryset.filter(timestamp__lte=end_time)
    
    queryset = queryset.order_by('-timestamp')
    
    if limit:
        queryset = queryset[:limit]
    
    return queryset


def get_tracking_logs_for_session(session_id, event_type=None, limit=None):
    """
    Get tracking logs for a session.
    
    Args:
        session_id: ID of the session
        event_type: Optional event type filter
        limit: Optional limit on the number of results
        
    Returns:
        Queryset of tracking logs
    """
    queryset = TrackingLog.objects.filter(session_id=session_id)
    
    if event_type:
        queryset = queryset.filter(event_type=event_type)
    
    queryset = queryset.order_by('-timestamp')
    
    if limit:
        queryset = queryset[:limit]
    
    return queryset


def get_latest_location_for_session(session_id):
    """
    Get the latest location update for a tracking session.
    
    Args:
        session_id: ID of the session
        
    Returns:
        LocationUpdate instance or None
    """
    # Check cache first
    cache_key = CACHE_KEY_LOCATION.format(session_id)
    cached_location = cache.get(cache_key)
    
    if cached_location:
        return cached_location
    
    # If not in cache, get from database
    latest_update = LocationUpdate.objects.filter(
        session_id=session_id
    ).order_by('-timestamp').first()
    
    return latest_update


def get_latest_locations_for_line(line_id):
    """
    Get the latest location updates for all active sessions on a line.
    
    Args:
        line_id: ID of the line
        
    Returns:
        List of location data dictionaries
    """
    # Get active sessions for the line
    active_sessions = get_active_sessions_for_line(line_id)
    
    if not active_sessions:
        return []
    
    # Get latest location for each session
    latest_locations = []
    
    for session in active_sessions:
        location = get_latest_location_for_session(session.id)
        
        if location:
            # If it's a cached dictionary, use it directly
            if isinstance(location, dict):
                latest_locations.append(location)
            else:
                # If it's a LocationUpdate object, convert to dict
                latest_locations.append({
                    'latitude': float(location.latitude),
                    'longitude': float(location.longitude),
                    'accuracy': location.accuracy,
                    'speed': location.speed,
                    'heading': location.heading,
                    'timestamp': location.timestamp.isoformat(),
                    'session_id': str(session.id),
                    'bus_id': str(session.bus.id),
                    'driver_id': str(session.driver.id),
                    'line_id': str(session.line.id),
                })
    
    return latest_locations


def get_session_statistics(session_id):
    """
    Get statistics for a tracking session.
    
    Args:
        session_id: ID of the session
        
    Returns:
        Dictionary of statistics
    """
    try:
        session = TrackingSession.objects.get(id=session_id)
    except TrackingSession.DoesNotExist:
        return None
    
    # Count location updates
    location_count = LocationUpdate.objects.filter(session=session).count()
    
    # Calculate total distance
    total_distance = session.total_distance
    
    # Calculate duration
    if session.end_time:
        duration = (session.end_time - session.start_time).total_seconds()
    else:
        duration = (timezone.now() - session.start_time).total_seconds()
    
    # Calculate average speed (m/s)
    if duration > 0:
        avg_speed = total_distance / duration
    else:
        avg_speed = 0
    
    return {
        'location_count': location_count,
        'total_distance': total_distance,
        'duration': duration,
        'average_speed': avg_speed,
    }


def get_unprocessed_offline_batches():
    """
    Get unprocessed offline location batches.
    
    Returns:
        Queryset of unprocessed offline location batches
    """
    return OfflineLocationBatch.objects.filter(
        processed=False,
        is_active=True,
    ).select_related(
        'driver', 'bus', 'line'
    ).order_by('collected_at')
