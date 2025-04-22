import logging
from celery import shared_task

from .services import (
    recalculate_etas_for_line,
    send_eta_notifications
)
from .models import ETA


logger = logging.getLogger(__name__)


@shared_task
def update_all_etas():
    from apps.lines.models import Line
    
    # Get all active lines
    active_lines = Line.objects.filter(is_active=True)
    
    updated_count = 0
    for line in active_lines:
        try:
            updates = recalculate_etas_for_line(line.id)
            updated_count += len(updates)
        except Exception as e:
            logger.error(f"Error updating ETAs for line {line.id}: {str(e)}")
    
    return f"Updated {updated_count} ETAs across {active_lines.count()} lines."


@shared_task
def notify_eta_changes():
    sent_count = send_eta_notifications()
    return f"Sent {sent_count} ETA notifications."


@shared_task
def cleanup_old_etas(days=1):
    from django.utils import timezone
    from datetime import timedelta
    
    # Get cutoff date
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old ETAs
    result = ETA.objects.filter(
        estimated_arrival_time__lt=cutoff_date
    ).delete()
    
    deleted_count = result[0] if result else 0
    
    return f"Deleted {deleted_count} old ETAs."


@shared_task
def mark_arrived_buses():
    from django.utils import timezone
    from apps.tracking.models import TrackingSession, LocationUpdate
    from apps.lines.models import LineStop
    
    # Get active tracking sessions
    active_sessions = TrackingSession.objects.filter(
        status='active',
        is_active=True
    ).select_related('line', 'bus')
    
    arrivals_count = 0
    
    for session in active_sessions:
        # Get latest location
        latest_location = LocationUpdate.objects.filter(
            session=session
        ).order_by('-timestamp').first()
        
        if not latest_location:
            continue
        
        # Get all stops for this line
        line_stops = LineStop.objects.filter(
            line=session.line
        ).select_related('stop').order_by('order')
        
        # Check if bus is near any stop
        for line_stop in line_stops:
            from utils.geo import calculate_distance
            
            # Calculate distance to stop
            distance = calculate_distance(
                latest_location.coordinates,
                line_stop.stop.coordinates
            )
            
            # If bus is within 50 meters of a stop, mark as arrived
            if distance <= 50:
                try:
                    from apps.eta.services import record_stop_arrival
                    arrival = record_stop_arrival(session.id, line_stop.stop.id)
                    if arrival:
                        arrivals_count += 1
                except Exception as e:
                    logger.error(f"Error recording arrival for session {session.id} at stop {line_stop.stop.id}: {str(e)}")
    
    return f"Recorded {arrivals_count} automatic stop arrivals."


@shared_task
def update_eta_statuses():
    from django.utils import timezone
    
    # Get ETAs that should be approaching (within 5 minutes)
    approaching_time = timezone.now() + timezone.timedelta(minutes=5)
    
    approaching_etas = ETA.objects.filter(
        status='scheduled',
        estimated_arrival_time__lte=approaching_time,
        estimated_arrival_time__gt=timezone.now(),
        is_active=True
    )
    
    # Update status to approaching
    approaching_count = approaching_etas.update(status='approaching')
    
    # Get ETAs that are delayed
    delayed_etas = ETA.objects.filter(
        status__in=['scheduled', 'approaching'],
        estimated_arrival_time__lt=timezone.now(),
        actual_arrival_time__isnull=True,
        is_active=True
    )
    
    # Update status to delayed and calculate delay minutes
    delayed_count = 0
    for eta in delayed_etas:
        delay = (timezone.now() - eta.estimated_arrival_time).total_seconds() / 60
        eta.status = 'delayed'
        eta.delay_minutes = int(delay)
        eta.save()
        delayed_count += 1
    
    return f"Updated {approaching_count} ETAs to approaching and {delayed_count} ETAs to delayed."
