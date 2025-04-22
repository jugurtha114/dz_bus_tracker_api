from datetime import datetime
import json
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction

from apps.core.constants import CACHE_KEY_LOCATION
from utils.geo import calculate_distance
from .models import TrackingSession, LocationUpdate, TrackingLog, OfflineLocationBatch


def start_tracking_session(driver, bus, line, schedule=None):
    """
    Start a new tracking session.
    
    Args:
        driver: Driver object
        bus: Bus object
        line: Line object
        schedule: Optional Schedule object
        
    Returns:
        Newly created TrackingSession
    """
    # Create the tracking session
    session = TrackingSession.objects.create(
        driver=driver,
        bus=bus,
        line=line,
        schedule=schedule,
        status='active',
        start_time=timezone.now(),
    )
    
    # Log the event
    log_tracking_event(
        session=session,
        event_type='session_started',
        message=f"Tracking session started for {bus} on {line}",
    )
    
    return session


def end_tracking_session(session_id):
    """
    End a tracking session.
    
    Args:
        session_id: ID of the session to end
        
    Returns:
        Updated TrackingSession
    """
    try:
        session = TrackingSession.objects.get(id=session_id, status='active')
    except TrackingSession.DoesNotExist:
        return None
    
    # End the session
    session.end_time = timezone.now()
    session.status = 'completed'
    session.save(update_fields=['end_time', 'status'])
    
    # Log the event
    log_tracking_event(
        session=session,
        event_type='session_ended',
        message=f"Tracking session ended for {session.bus} on {session.line}",
        data={
            'duration': (session.end_time - session.start_time).total_seconds(),
            'total_distance': session.total_distance,
        }
    )
    
    # Generate trip metrics
    from apps.analytics.services import create_trip_log
    create_trip_log(session)
    
    # Update ETAs
    from apps.eta.services import recalculate_etas_for_line
    recalculate_etas_for_line(session.line.id)
    
    return session


def pause_tracking_session(session_id):
    """
    Pause a tracking session.
    
    Args:
        session_id: ID of the session to pause
        
    Returns:
        Updated TrackingSession
    """
    try:
        session = TrackingSession.objects.get(id=session_id, status='active')
    except TrackingSession.DoesNotExist:
        return None
    
    # Pause the session
    session.status = 'paused'
    session.save(update_fields=['status'])
    
    # Log the event
    log_tracking_event(
        session=session,
        event_type='session_paused',
        message=f"Tracking session paused for {session.bus} on {session.line}",
    )
    
    return session


def resume_tracking_session(session_id):
    """
    Resume a paused tracking session.
    
    Args:
        session_id: ID of the session to resume
        
    Returns:
        Updated TrackingSession
    """
    try:
        session = TrackingSession.objects.get(id=session_id, status='paused')
    except TrackingSession.DoesNotExist:
        return None
    
    # Resume the session
    session.status = 'active'
    session.save(update_fields=['status'])
    
    # Log the event
    log_tracking_event(
        session=session,
        event_type='session_resumed',
        message=f"Tracking session resumed for {session.bus} on {session.line}",
    )
    
    return session


def add_location_update(session_id, location_data):
    """
    Add a location update to a tracking session.
    
    Args:
        session_id: ID of the session
        location_data: Dictionary containing location data
        
    Returns:
        Newly created LocationUpdate
    """
    try:
        session = TrackingSession.objects.get(id=session_id)
    except TrackingSession.DoesNotExist:
        return None
    
    if session.status != 'active':
        log_tracking_event(
            session=session,
            event_type='location_update_rejected',
            message="Location update rejected: session not active",
            data=location_data
        )
        return None
    
    # Create the location update
    location_update = LocationUpdate.objects.create(
        session=session,
        latitude=location_data.get('latitude'),
        longitude=location_data.get('longitude'),
        accuracy=location_data.get('accuracy'),
        speed=location_data.get('speed'),
        heading=location_data.get('heading'),
        altitude=location_data.get('altitude'),
        timestamp=location_data.get('timestamp') or timezone.now(),
        metadata=location_data.get('metadata', {}),
    )
    
    # Cache the latest location
    cache_key = CACHE_KEY_LOCATION.format(session.id)
    cache.set(
        cache_key,
        {
            'latitude': float(location_update.latitude),
            'longitude': float(location_update.longitude),
            'accuracy': location_update.accuracy,
            'speed': location_update.speed,
            'heading': location_update.heading,
            'timestamp': location_update.timestamp.isoformat(),
            'session_id': str(session.id),
            'bus_id': str(session.bus.id),
            'driver_id': str(session.driver.id),
            'line_id': str(session.line.id),
        },
        timeout=3600  # 1 hour
    )
    
    # Check if we need to recalculate ETAs
    from apps.eta.services import should_recalculate_eta, recalculate_etas_for_line
    if should_recalculate_eta(session.line.id, location_update):
        recalculate_etas_for_line(session.line.id)
    
    return location_update


@transaction.atomic
def batch_location_updates(session_id, locations):
    """
    Add multiple location updates to a tracking session.
    
    Args:
        session_id: ID of the session
        locations: List of dictionaries containing location data
        
    Returns:
        List of created LocationUpdate objects
    """
    try:
        session = TrackingSession.objects.get(id=session_id)
    except TrackingSession.DoesNotExist:
        return []
    
    if session.status != 'active':
        log_tracking_event(
            session=session,
            event_type='batch_location_update_rejected',
            message="Batch location update rejected: session not active",
            data={'count': len(locations)}
        )
        return []
    
    # Sort locations by timestamp
    sorted_locations = sorted(
        locations,
        key=lambda x: x.get('timestamp') or timezone.now()
    )
    
    created_updates = []
    latest_update = None
    
    for location_data in sorted_locations:
        # Convert timestamp if it's a string
        if isinstance(location_data.get('timestamp'), str):
            try:
                location_data['timestamp'] = datetime.fromisoformat(
                    location_data['timestamp'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                location_data['timestamp'] = timezone.now()
        
        # Create the location update
        location_update = LocationUpdate.objects.create(
            session=session,
            latitude=location_data.get('latitude'),
            longitude=location_data.get('longitude'),
            accuracy=location_data.get('accuracy'),
            speed=location_data.get('speed'),
            heading=location_data.get('heading'),
            altitude=location_data.get('altitude'),
            timestamp=location_data.get('timestamp') or timezone.now(),
            metadata=location_data.get('metadata', {}),
        )
        
        created_updates.append(location_update)
        latest_update = location_update
    
    # Cache the latest location
    if latest_update:
        cache_key = CACHE_KEY_LOCATION.format(session.id)
        cache.set(
            cache_key,
            {
                'latitude': float(latest_update.latitude),
                'longitude': float(latest_update.longitude),
                'accuracy': latest_update.accuracy,
                'speed': latest_update.speed,
                'heading': latest_update.heading,
                'timestamp': latest_update.timestamp.isoformat(),
                'session_id': str(session.id),
                'bus_id': str(session.bus.id),
                'driver_id': str(session.driver.id),
                'line_id': str(session.line.id),
            },
            timeout=3600  # 1 hour
        )
    
    # Log the event
    log_tracking_event(
        session=session,
        event_type='batch_location_update',
        message=f"Added {len(created_updates)} location updates in batch",
        data={'count': len(created_updates)}
    )
    
    # Check if we need to recalculate ETAs
    from apps.eta.services import should_recalculate_eta, recalculate_etas_for_line
    if latest_update and should_recalculate_eta(session.line.id, latest_update):
        recalculate_etas_for_line(session.line.id)
    
    return created_updates


def create_offline_batch(driver, bus, line, location_data):
    """
    Create an offline location batch.
    
    Args:
        driver: Driver object
        bus: Bus object
        line: Line object
        location_data: List of dictionaries containing location data
        
    Returns:
        Newly created OfflineLocationBatch
    """
    batch = OfflineLocationBatch.objects.create(
        driver=driver,
        bus=bus,
        line=line,
        data=location_data,
    )
    
    return batch


@transaction.atomic
def process_offline_batch(batch):
    """
    Process an offline location batch.
    
    Args:
        batch: OfflineLocationBatch object
        
    Returns:
        Boolean indicating success
    """
    if batch.processed:
        return True
    
    # Find or create a tracking session
    session = None
    
    # Check for an active session for this bus
    active_session = TrackingSession.objects.filter(
        bus=batch.bus,
        status='active',
    ).first()
    
    if active_session:
        session = active_session
    else:
        # Create a new session
        session = start_tracking_session(
            driver=batch.driver,
            bus=batch.bus,
            line=batch.line,
        )
    
    # Process the location data
    batch_location_updates(session.id, batch.data)
    
    return True


def log_tracking_event(session, event_type, message="", data=None):
    """
    Log a tracking event.
    
    Args:
        session: TrackingSession object
        event_type: Type of event
        message: Optional message
        data: Optional data dictionary
        
    Returns:
        Newly created TrackingLog
    """
    log = TrackingLog.objects.create(
        session=session,
        event_type=event_type,
        message=message,
        data=data or {},
        timestamp=timezone.now(),
    )
    
    return log


def get_current_location(session_id):
    """
    Get the current location of a tracking session.
    
    Args:
        session_id: ID of the session
        
    Returns:
        Dictionary containing location data, or None if not found
    """
    # Check cache first
    cache_key = CACHE_KEY_LOCATION.format(session_id)
    cached_location = cache.get(cache_key)
    
    if cached_location:
        return cached_location
    
    # If not in cache, get from database
    try:
        session = TrackingSession.objects.get(id=session_id)
        latest_update = LocationUpdate.objects.filter(
            session=session
        ).order_by('-timestamp').first()
        
        if not latest_update:
            return None
        
        # Build location data
        location_data = {
            'latitude': float(latest_update.latitude),
            'longitude': float(latest_update.longitude),
            'accuracy': latest_update.accuracy,
            'speed': latest_update.speed,
            'heading': latest_update.heading,
            'timestamp': latest_update.timestamp.isoformat(),
            'session_id': str(session.id),
            'bus_id': str(session.bus.id),
            'driver_id': str(session.driver.id),
            'line_id': str(session.line.id),
        }
        
        # Cache the data
        cache.set(cache_key, location_data, timeout=3600)  # 1 hour
        
        return location_data
    
    except (TrackingSession.DoesNotExist, AttributeError):
        return None
