import logging
from datetime import timedelta
from django.utils import timezone
from celery import shared_task

from .models import TrackingSession, LocationUpdate, OfflineLocationBatch
from .selectors import get_unprocessed_offline_batches, get_active_tracking_sessions
from .services import process_offline_batch, end_tracking_session, log_tracking_event


logger = logging.getLogger(__name__)


@shared_task
def process_offline_batches():
    """
    Process all unprocessed offline location batches.
    """
    batches = get_unprocessed_offline_batches()
    
    processed_count = 0
    for batch in batches:
        try:
            success = process_offline_batch(batch)
            if success:
                processed_count += 1
        except Exception as e:
            logger.error(f"Error processing offline batch {batch.id}: {str(e)}")
    
    return f"Processed {processed_count} offline batches."


@shared_task
def cleanup_old_location_data(days=30):
    """
    Clean up old location data.
    
    Args:
        days: Number of days to keep
    """
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete location updates older than cutoff date
    result = LocationUpdate.objects.filter(
        timestamp__lt=cutoff_date
    ).delete()
    
    deleted_count = result[0] if result else 0
    
    return f"Deleted {deleted_count} old location updates."


@shared_task
def close_inactive_sessions(inactive_minutes=60):
    """
    Close tracking sessions that have been inactive for a while.
    
    Args:
        inactive_minutes: Minutes of inactivity before closing
    """
    cutoff_time = timezone.now() - timedelta(minutes=inactive_minutes)
    
    # Get active sessions with no recent updates
    sessions = TrackingSession.objects.filter(
        status='active',
        is_active=True,
        last_update__lt=cutoff_time
    )
    
    closed_count = 0
    for session in sessions:
        try:
            # Log the event
            log_tracking_event(
                session=session,
                event_type='session_auto_closed',
                message=f"Session automatically closed due to {inactive_minutes} minutes of inactivity",
            )
            
            # End the session
            end_tracking_session(session.id)
            closed_count += 1
        except Exception as e:
            logger.error(f"Error closing inactive session {session.id}: {str(e)}")
    
    return f"Closed {closed_count} inactive tracking sessions."


@shared_task
def check_tracking_gaps():
    """
    Check for gaps in tracking data for active sessions.
    """
    sessions = get_active_tracking_sessions()
    
    gap_threshold = timedelta(minutes=5)
    current_time = timezone.now()
    
    gap_count = 0
    for session in sessions:
        if not session.last_update:
            continue
        
        time_since_update = current_time - session.last_update
        
        if time_since_update > gap_threshold:
            # Log the tracking gap
            log_tracking_event(
                session=session,
                event_type='tracking_gap_detected',
                message=f"No location updates for {time_since_update.total_seconds() // 60} minutes",
                data={
                    'minutes_since_update': time_since_update.total_seconds() // 60,
                    'last_update': session.last_update.isoformat(),
                }
            )
            gap_count += 1
    
    return f"Detected {gap_count} tracking gaps."


@shared_task
def calculate_trip_metrics():
    """
    Calculate metrics for all completed trips that haven't been processed.
    """
    from apps.analytics.services import create_trip_logs_for_completed_sessions
    
    processed_count = create_trip_logs_for_completed_sessions()
    
    return f"Processed metrics for {processed_count} completed trips."


@shared_task
def sync_tracking_data_with_analytics():
    """
    Sync tracking data with analytics.
    """
    from apps.analytics.services import update_analytics_from_tracking
    
    updated_count = update_analytics_from_tracking()
    
    return f"Updated analytics for {updated_count} sessions."


@shared_task
def handle_stuck_sessions(hours=12):
    """
    Handle sessions that are stuck in active state for too long.
    
    Args:
        hours: Maximum hours a session can be active
    """
    cutoff_time = timezone.now() - timedelta(hours=hours)
    
    # Get active sessions that started too long ago
    sessions = TrackingSession.objects.filter(
        status='active',
        is_active=True,
        start_time__lt=cutoff_time
    )
    
    handled_count = 0
    for session in sessions:
        try:
            # Log the event
            log_tracking_event(
                session=session,
                event_type='session_stuck',
                message=f"Session active for more than {hours} hours",
                data={
                    'hours_active': (timezone.now() - session.start_time).total_seconds() // 3600,
                }
            )
            
            # End the session
            end_tracking_session(session.id)
            handled_count += 1
        except Exception as e:
            logger.error(f"Error handling stuck session {session.id}: {str(e)}")
    
    return f"Handled {handled_count} stuck tracking sessions."
