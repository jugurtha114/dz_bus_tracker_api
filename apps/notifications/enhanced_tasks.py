"""
Enhanced Celery tasks for professional notification system.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.core.constants import NOTIFICATION_CHANNEL_PUSH
from apps.core.exceptions import ValidationError

from .models import NotificationSchedule, DeviceToken, Notification
from .enhanced_services import EnhancedNotificationService, EnhancedDeviceTokenService
from .firebase import FCMService, FCMPriority

logger = logging.getLogger(__name__)


@shared_task(name="notifications.process_scheduled_notifications", bind=True)
def process_scheduled_notifications(self):
    """
    Process and send scheduled notifications with enhanced error handling.
    """
    try:
        # Get due notifications
        due_notifications = NotificationSchedule.objects.filter(
            is_sent=False,
            scheduled_for__lte=timezone.now()
        ).select_related('user', 'bus', 'stop', 'line', 'trip')

        if not due_notifications.exists():
            logger.info("No scheduled notifications to process")
            return {"processed": 0, "failed": 0}

        processed_count = 0
        failed_count = 0
        total_count = due_notifications.count()

        logger.info(f"Processing {total_count} scheduled notifications")

        for i, scheduled in enumerate(due_notifications):
            try:
                # Update task progress
                self.update_state(
                    state='PROGRESS',
                    meta={'current': i + 1, 'total': total_count}
                )

                # Prepare template kwargs from scheduled data
                template_kwargs = scheduled.data.copy()
                
                # Add related object data
                if scheduled.bus:
                    template_kwargs.update({
                        'bus_id': str(scheduled.bus.id),
                        'bus_number': scheduled.bus.bus_number
                    })
                
                if scheduled.stop:
                    template_kwargs.update({
                        'stop_id': str(scheduled.stop.id),
                        'stop_name': scheduled.stop.name
                    })
                
                if scheduled.line:
                    template_kwargs.update({
                        'line_id': str(scheduled.line.id),
                        'line_name': scheduled.line.name
                    })
                
                if scheduled.trip:
                    template_kwargs['trip_id'] = str(scheduled.trip.id)

                # Send notification using enhanced service
                result = EnhancedNotificationService.send_notification(
                    user_id=str(scheduled.user.id),
                    template_type=scheduled.notification_type,
                    channels=scheduled.channels,
                    **template_kwargs
                )

                # Mark as sent
                scheduled.is_sent = True
                scheduled.sent_at = timezone.now()
                
                if not result.get('success'):
                    scheduled.error = result.get('error', 'Unknown error')
                else:
                    scheduled.error = ''
                
                scheduled.save()
                processed_count += 1

            except Exception as e:
                logger.error(f"Failed to send scheduled notification {scheduled.id}: {e}")
                scheduled.error = str(e)
                scheduled.save()
                failed_count += 1

        logger.info(f"Processed {processed_count} scheduled notifications, {failed_count} failed")
        
        # Cache results for monitoring
        cache.set('notifications:last_scheduled_run', {
            'timestamp': timezone.now().isoformat(),
            'processed': processed_count,
            'failed': failed_count,
            'total': total_count
        }, 3600)
        
        return {
            "success": True,
            "processed": processed_count,
            "failed": failed_count,
            "total": total_count
        }

    except Exception as e:
        logger.error(f"Error processing scheduled notifications: {e}")
        return {"success": False, "error": str(e)}


@shared_task(name="notifications.cleanup_invalid_tokens", bind=True)
def cleanup_invalid_tokens(self, batch_size=100):
    """
    Clean up invalid device tokens with batch processing.
    """
    try:
        logger.info("Starting invalid token cleanup")
        
        # Use enhanced service for cleanup
        cleaned_count = EnhancedDeviceTokenService.cleanup_invalid_tokens(batch_size)
        
        # Also clean tokens older than 90 days with no activity
        cutoff_date = timezone.now() - timedelta(days=90)
        old_tokens_count = DeviceToken.objects.filter(
            last_used__lt=cutoff_date,
            is_active=True
        ).update(
            is_active=False,
            updated_at=timezone.now()
        )
        
        total_cleaned = cleaned_count + old_tokens_count
        
        logger.info(f"Token cleanup completed: {total_cleaned} tokens deactivated")
        
        # Cache results for monitoring
        cache.set('notifications:last_token_cleanup', {
            'timestamp': timezone.now().isoformat(),
            'invalid_tokens_cleaned': cleaned_count,
            'old_tokens_cleaned': old_tokens_count,
            'total_cleaned': total_cleaned
        }, 3600)
        
        return {
            "success": True,
            "invalid_tokens_cleaned": cleaned_count,
            "old_tokens_cleaned": old_tokens_count,
            "total_cleaned": total_cleaned
        }

    except Exception as e:
        logger.error(f"Error cleaning up invalid tokens: {e}")
        return {"success": False, "error": str(e)}


@shared_task(name="notifications.send_bulk_notification")
def send_bulk_notification_task(
    user_ids: List[str],
    template_type: str,
    channels: List[str],
    priority: str = 'normal',
    **template_kwargs
) -> Dict[str, Any]:
    """
    Send bulk notifications efficiently.
    """
    try:
        priority_enum = FCMPriority.HIGH if priority == 'high' else FCMPriority.NORMAL
        
        # If sending push notifications to many users, use FCM topics for efficiency
        if NOTIFICATION_CHANNEL_PUSH in channels and len(user_ids) > 50:
            # TODO: Implement topic-based messaging for large audiences
            pass
        
        # Process users in batches to avoid memory issues
        batch_size = 50
        total_sent = 0
        total_failed = 0
        
        for i in range(0, len(user_ids), batch_size):
            batch_user_ids = user_ids[i:i + batch_size]
            
            for user_id in batch_user_ids:
                try:
                    result = EnhancedNotificationService.send_notification(
                        user_id=user_id,
                        template_type=template_type,
                        channels=channels,
                        priority=priority_enum,
                        **template_kwargs
                    )
                    
                    if result.get('success'):
                        total_sent += 1
                    else:
                        total_failed += 1
                        logger.warning(f"Failed to send to user {user_id}: {result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Failed to send notification to user {user_id}: {e}")
                    total_failed += 1
        
        logger.info(
            f"Bulk notification completed: {total_sent} sent, {total_failed} failed"
        )
        
        return {
            'success': True,
            'total_sent': total_sent,
            'total_failed': total_failed,
            'user_count': len(user_ids)
        }
        
    except Exception as e:
        logger.error(f"Bulk notification task failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name="notifications.health_check")
def notification_health_check():
    """
    Perform health check on notification system.
    """
    try:
        health_data = {
            'timestamp': timezone.now().isoformat(),
            'firebase_initialized': FCMService.is_initialized(),
            'active_tokens_count': DeviceToken.objects.filter(is_active=True).count(),
            'pending_schedules_count': NotificationSchedule.objects.filter(
                is_sent=False,
                scheduled_for__lte=timezone.now()
            ).count(),
            'recent_notifications_count': Notification.objects.filter(
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
        }
        
        # Test Firebase connection
        if FCMService.is_initialized():
            fcm_stats = FCMService.get_stats()
            health_data['fcm_stats'] = fcm_stats
        
        # Cache health data
        cache.set('notifications:health_check', health_data, 300)  # 5 minutes
        
        logger.info("Notification system health check completed")
        return health_data
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name="notifications.check_arrival_notifications")
def check_arrival_notifications():
    """
    Enhanced arrival notification checking with better logic.
    """
    try:
        from apps.tracking.models import Trip
        from apps.tracking.services.route_service import RouteService
        from .models import NotificationPreference
        
        # Get active trips
        active_trips = Trip.objects.filter(
            end_time__isnull=True
        ).select_related('bus', 'line', 'driver')
        
        processed_trips = 0
        notifications_scheduled = 0
        
        for trip in active_trips:
            try:
                # Get route estimation
                route_data = RouteService.get_estimated_route(str(trip.bus.id))
                if not route_data or 'remaining_stops' not in route_data:
                    continue
                
                # Check each upcoming stop
                for stop_info in route_data['remaining_stops'][:3]:  # Next 3 stops
                    stop_id = stop_info.get('id')
                    eta_minutes = stop_info.get('travel_time_minutes', 0)
                    
                    if not stop_id or eta_minutes > 30:
                        continue
                    
                    # Find users who want notifications for this stop
                    preferences = NotificationPreference.objects.filter(
                        notification_type='bus_arrival',
                        enabled=True,
                        favorite_stops__id=stop_id
                    ).select_related('user')
                    
                    for pref in preferences:
                        # Check if notification should be scheduled
                        if eta_minutes <= pref.minutes_before_arrival + 2:
                            estimated_arrival = timezone.now() + timedelta(minutes=eta_minutes)
                            
                            # Use enhanced service to schedule
                            result = EnhancedNotificationService.send_notification(
                                user_id=str(pref.user.id),
                                template_type='bus_arrival',
                                channels=pref.channels,
                                bus_id=str(trip.bus.id),
                                bus_number=trip.bus.bus_number,
                                stop_id=stop_id,
                                stop_name=stop_info.get('name', 'Unknown Stop'),
                                line_id=str(trip.line.id),
                                minutes=eta_minutes,
                                estimated_arrival=estimated_arrival.isoformat()
                            )
                            
                            if result.get('success'):
                                notifications_scheduled += 1
                
                processed_trips += 1
                
            except Exception as e:
                logger.error(f"Error processing trip {trip.id}: {e}")
                continue
        
        logger.info(f"Processed {processed_trips} trips, scheduled {notifications_scheduled} notifications")
        
        return {
            'success': True,
            'trips_processed': processed_trips,
            'notifications_scheduled': notifications_scheduled
        }
        
    except Exception as e:
        logger.error(f"Error checking arrival notifications: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name="notifications.test_push_notification")
def test_push_notification(user_id: str, message: str = "Test notification"):
    """
    Send a test push notification to a user.
    """
    try:
        result = EnhancedNotificationService.send_notification(
            user_id=user_id,
            template_type='service_alert',
            channels=['push'],
            priority=FCMPriority.NORMAL,
            title="Test Notification",
            message=message,
            severity='info'
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Test notification failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name="notifications.clean_old_data")
def clean_old_data(days=30):
    """
    Clean old notifications and schedules.
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Clean old read notifications
        old_notifications_count, _ = Notification.objects.filter(
            is_read=True,
            read_at__lt=cutoff_date
        ).delete()
        
        # Clean old sent scheduled notifications
        old_schedules_count, _ = NotificationSchedule.objects.filter(
            is_sent=True,
            sent_at__lt=cutoff_date
        ).delete()
        
        logger.info(
            f"Cleaned {old_notifications_count} old notifications and "
            f"{old_schedules_count} old scheduled notifications"
        )
        
        return {
            "success": True,
            "notifications_cleaned": old_notifications_count,
            "schedules_cleaned": old_schedules_count
        }
        
    except Exception as e:
        logger.error(f"Error cleaning old data: {e}")
        return {"success": False, "error": str(e)}