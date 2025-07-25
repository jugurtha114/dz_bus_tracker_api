"""
Celery tasks for the notifications app.
"""
import logging
from celery import shared_task
from django.utils import timezone

from .services import NotificationService

logger = logging.getLogger(__name__)


@shared_task(name='notifications.process_scheduled')
def process_scheduled_notifications():
    """
    Process and send all due scheduled notifications.
    This task should run every minute via Celery Beat.
    """
    try:
        NotificationService.process_scheduled_notifications()
        logger.info("Successfully processed scheduled notifications")
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"Error processing scheduled notifications: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='notifications.cleanup_old_notifications')
def cleanup_old_notifications(days=30):
    """
    Clean up old read notifications.
    
    Args:
        days: Number of days to keep read notifications
    """
    try:
        from .models import Notification
        
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        
        # Delete old read notifications
        count, _ = Notification.objects.filter(
            is_read=True,
            read_at__lt=cutoff_date
        ).delete()
        
        logger.info(f"Deleted {count} old notifications")
        return {'status': 'success', 'deleted': count}
    except Exception as e:
        logger.error(f"Error cleaning up notifications: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='notifications.check_arrival_notifications')
def check_arrival_notifications():
    """
    Check for buses approaching stops and schedule notifications.
    This task should run every 2-3 minutes.
    """
    try:
        from apps.tracking.models import LocationUpdate, Trip
        from apps.tracking.services.route_service import RouteService
        from .models import NotificationPreference
        
        # Get active trips
        active_trips = Trip.objects.filter(
            end_time__isnull=True
        ).select_related('bus', 'line', 'driver')
        
        for trip in active_trips:
            # Get latest location
            latest_location = LocationUpdate.objects.filter(
                bus=trip.bus
            ).order_by('-timestamp').first()
            
            if not latest_location:
                continue
            
            # Get upcoming stops
            try:
                route_data = RouteService.estimate_route(str(trip.bus.id))
                if not route_data or 'remaining_stops' not in route_data:
                    continue
                
                # Check each upcoming stop
                for stop_info in route_data['remaining_stops'][:3]:  # Check next 3 stops
                    stop_id = stop_info.get('id')
                    eta_minutes = stop_info.get('travel_time_minutes', 0)
                    
                    if not stop_id or eta_minutes > 30:  # Only notify for stops within 30 minutes
                        continue
                    
                    # Find users who want notifications for this stop
                    preferences = NotificationPreference.objects.filter(
                        notification_type='arrival',
                        enabled=True,
                        favorite_stops__id=stop_id
                    ).select_related('user')
                    
                    for pref in preferences:
                        # Check if we should notify (within their preferred time window)
                        if eta_minutes <= pref.minutes_before_arrival + 2:  # 2 minute buffer
                            # Calculate estimated arrival time
                            estimated_arrival = timezone.now() + timezone.timedelta(minutes=eta_minutes)
                            
                            # Schedule notification
                            NotificationService.schedule_arrival_notification(
                                user_id=str(pref.user.id),
                                bus_id=str(trip.bus.id),
                                stop_id=stop_id,
                                estimated_arrival=estimated_arrival,
                                trip_id=str(trip.id)
                            )
            
            except Exception as e:
                logger.error(f"Error processing trip {trip.id}: {e}")
                continue
        
        logger.info(f"Processed {active_trips.count()} active trips for arrival notifications")
        return {'status': 'success', 'trips_processed': active_trips.count()}
        
    except Exception as e:
        logger.error(f"Error checking arrival notifications: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='notifications.send_trip_updates')
def send_trip_updates():
    """
    Send notifications for trip starts and ends.
    This task should run every minute.
    """
    try:
        from datetime import timedelta
        from apps.tracking.models import Trip
        from .models import NotificationPreference
        
        # Check for recently started trips (last 2 minutes)
        recent_start = timezone.now() - timedelta(minutes=2)
        new_trips = Trip.objects.filter(
            start_time__gte=recent_start
        ).select_related('bus', 'line', 'driver')
        
        for trip in new_trips:
            # Find users interested in this line
            preferences = NotificationPreference.objects.filter(
                notification_type='trip_start',
                enabled=True,
                favorite_lines=trip.line
            )
            
            for pref in preferences:
                NotificationService.create_notification(
                    user_id=str(pref.user.id),
                    notification_type='trip_start',
                    title=f"Trip Started - {trip.line.name}",
                    message=f"Bus {trip.bus.bus_number} has started its trip on line {trip.line.name}",
                    data={
                        'trip_id': str(trip.id),
                        'bus_id': str(trip.bus.id),
                        'line_id': str(trip.line.id)
                    }
                )
        
        # Check for recently ended trips
        recent_end = timezone.now() - timedelta(minutes=2)
        ended_trips = Trip.objects.filter(
            end_time__gte=recent_end,
            end_time__lt=timezone.now()
        ).select_related('bus', 'line', 'driver')
        
        for trip in ended_trips:
            # Find users interested in this line
            preferences = NotificationPreference.objects.filter(
                notification_type='trip_end',
                enabled=True,
                favorite_lines=trip.line
            )
            
            for pref in preferences:
                NotificationService.create_notification(
                    user_id=str(pref.user.id),
                    notification_type='trip_end',
                    title=f"Trip Ended - {trip.line.name}",
                    message=f"Bus {trip.bus.bus_number} has completed its trip on line {trip.line.name}",
                    data={
                        'trip_id': str(trip.id),
                        'bus_id': str(trip.bus.id),
                        'line_id': str(trip.line.id),
                        'duration_minutes': int((trip.end_time - trip.start_time).total_seconds() / 60)
                    }
                )
        
        logger.info(f"Sent notifications for {new_trips.count()} new trips and {ended_trips.count()} ended trips")
        return {
            'status': 'success',
            'new_trips': new_trips.count(),
            'ended_trips': ended_trips.count()
        }
        
    except Exception as e:
        logger.error(f"Error sending trip updates: {e}")
        return {'status': 'error', 'message': str(e)}