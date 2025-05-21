"""
Selector functions for the notifications app.
"""
import logging

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.selectors import get_object_or_404

from .models import DeviceToken, Notification

logger = logging.getLogger(__name__)


def get_user_notifications(user_id, unread_only=False, limit=None):
    """
    Get notifications for a user.

    Args:
        user_id: ID of the user
        unread_only: Whether to get only unread notifications
        limit: Maximum number of notifications to return

    Returns:
        Queryset of Notification objects
    """
    queryset = Notification.objects.filter(user_id=user_id)

    if unread_only:
        queryset = queryset.filter(is_read=False)

    queryset = queryset.order_by('-created_at')

    if limit:
        queryset = queryset[:limit]

    return queryset


def get_notification_by_id(notification_id):
    """
    Get a notification by ID.

    Args:
        notification_id: ID of the notification

    Returns:
        Notification object
    """
    return get_object_or_404(Notification, id=notification_id)


def get_unread_notification_count(user_id):
    """
    Get the number of unread notifications for a user.

    Args:
        user_id: ID of the user

    Returns:
        Number of unread notifications
    """
    return Notification.objects.filter(
        user_id=user_id,
        is_read=False
    ).count()


def get_user_device_tokens(user_id, active_only=True):
    """
    Get device tokens for a user.

    Args:
        user_id: ID of the user
        active_only: Whether to get only active tokens

    Returns:
        Queryset of DeviceToken objects
    """
    queryset = DeviceToken.objects.filter(user_id=user_id)

    if active_only:
        queryset = queryset.filter(is_active=True)

    return queryset


def get_device_token_by_id(token_id):
    """
    Get a device token by ID.

    Args:
        token_id: ID of the device token

    Returns:
        DeviceToken object
    """
    return get_object_or_404(DeviceToken, id=token_id)


def user_has_device_token(user_id, token):
    """
    Check if a user has a specific device token.

    Args:
        user_id: ID of the user
        token: Device token

    Returns:
        Boolean indicating if the user has the token
    """
    return DeviceToken.objects.filter(
        user_id=user_id,
        token=token,
        is_active=True
    ).exists()


def get_notification_stats(user_id):
    """
    Get notification statistics for a user.

    Args:
        user_id: ID of the user

    Returns:
        Dictionary of notification statistics
    """
    total = Notification.objects.filter(user_id=user_id).count()
    unread = Notification.objects.filter(user_id=user_id, is_read=False).count()

    # Count by type
    type_counts = Notification.objects.filter(
        user_id=user_id
    ).values('notification_type').annotate(
        count=Count('id')
    )

    # Count by channel
    channel_counts = Notification.objects.filter(
        user_id=user_id
    ).values('channel').annotate(
        count=Count('id')
    )

    # Recent activity
    last_week = timezone.now() - timezone.timedelta(days=7)
    recent_count = Notification.objects.filter(
        user_id=user_id,
        created_at__gte=last_week
    ).count()

    return {
        "total": total,
        "unread": unread,
        "read_percentage": (total - unread) / total * 100 if total > 0 else 0,
        "type_counts": {item["notification_type"]: item["count"] for item in type_counts},
        "channel_counts": {item["channel"]: item["count"] for item in channel_counts},
        "recent_count": recent_count,
    }