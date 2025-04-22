import logging
from celery import shared_task

from .services import (
    cleanup_expired_notifications,
    mark_notifications_as_read
)
from .selectors import (
    get_expired_notifications,
    get_inactive_push_tokens
)


logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_notifications(days=30):
    result = cleanup_expired_notifications(days=days)
    return f"Cleaned up {result['expired_by_date_count']} expired and {result['old_read_count']} old read notifications."


@shared_task
def delete_inactive_push_tokens(days=90):
    tokens = get_inactive_push_tokens(days=days)
    count = tokens.count()
    
    if count > 0:
        tokens.delete()
    
    return f"Deleted {count} inactive push tokens."


@shared_task
def process_notification_queue():
    from django.db import connection
    
    # This task would process any pending notifications in a queue
    # For now, just a placeholder as notifications are sent in real-time
    
    # Close DB connections
    connection.close()
    
    return "Processed notification queue."


@shared_task
def auto_mark_expired_notifications_as_read():
    # Get expired notifications
    expired = get_expired_notifications()
    
    if not expired.exists():
        return "No expired notifications to mark as read."
    
    # Extract IDs
    notification_ids = [str(n.id) for n in expired]
    
    # Mark as read
    updated_count = mark_notifications_as_read(notification_ids)
    
    return f"Marked {updated_count} expired notifications as read."
