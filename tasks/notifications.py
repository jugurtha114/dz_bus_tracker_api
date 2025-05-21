"""
Celery tasks for notification-related operations.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.notifications.models import DeviceToken, Notification
from tasks.base import RetryableTask

logger = logging.getLogger(__name__)


@shared_task(base=RetryableTask)
def send_push_notifications():
    """
    Send pending push notifications.
    """
    try:
        # Get pending push notifications
        pending_notifications = Notification.objects.filter(
            channel="push",
            push_sent=False,
        ).select_related("user")

        # Group notifications by user
        user_notifications = {}

        for notification in pending_notifications:
            user_id = notification.user_id
            if user_id not in user_notifications:
                user_notifications[user_id] = []

            user_notifications[user_id].append(notification)

        # Process each user's notifications
        for user_id, notifications in user_notifications.items():
            # Get user's device tokens
            from apps.notifications.selectors import get_user_device_tokens
            tokens = get_user_device_tokens(user_id)

            if not tokens:
                logger.warning(f"No device tokens for user {user_id}")
                continue

            # Send notifications
            for notification in notifications:
                from apps.notifications.services import NotificationService
                success = NotificationService.send_push_notification(notification)

                if success:
                    notification.push_sent = True
                    notification.push_sent_at = timezone.now()
                    notification.save(update_fields=["push_sent", "push_sent_at"])

        logger.info(f"Processed {pending_notifications.count()} push notifications")
        return True

    except Exception as e:
        logger.error(f"Error sending push notifications: {e}")
        return False


@shared_task(base=RetryableTask)
def send_email_notifications():
    """
    Send pending email notifications.
    """
    try:
        # Get pending email notifications
        pending_notifications = Notification.objects.filter(
            channel="email",
            email_sent=False,
        ).select_related("user")

        # Process each notification
        for notification in pending_notifications:
            from apps.notifications.services import NotificationService
            success = NotificationService.send_email_notification(notification)

            if success:
                notification.email_sent = True
                notification.email_sent_at = timezone.now()
                notification.save(update_fields=["email_sent", "email_sent_at"])

        logger.info(f"Processed {pending_notifications.count()} email notifications")
        return True

    except Exception as e:
        logger.error(f"Error sending email notifications: {e}")
        return False


@shared_task(base=RetryableTask)
def send_sms_notifications():
    """
    Send pending SMS notifications.
    """
    try:
        # Get pending SMS notifications
        pending_notifications = Notification.objects.filter(
            channel="sms",
            sms_sent=False,
        ).select_related("user")

        # Process each notification
        for notification in pending_notifications:
            from apps.notifications.services import NotificationService
            success = NotificationService.send_sms_notification(notification)

            if success:
                notification.sms_sent = True
                notification.sms_sent_at = timezone.now()
                notification.save(update_fields=["sms_sent", "sms_sent_at"])

        logger.info(f"Processed {pending_notifications.count()} SMS notifications")
        return True

    except Exception as e:
        logger.error(f"Error sending SMS notifications: {e}")
        return False


@shared_task(base=RetryableTask)
def clean_old_notifications():
    """
    Clean old notifications to prevent database bloat.
    """
    try:
        # Define retention period (e.g., keep read notifications for 30 days)
        read_cutoff_date = timezone.now() - timedelta(days=30)

        # Define retention period for unread notifications (e.g., 90 days)
        unread_cutoff_date = timezone.now() - timedelta(days=90)

        # Delete old read notifications
        read_count = Notification.objects.filter(
            is_read=True,
            read_at__lt=read_cutoff_date,
        ).delete()[0]

        # Delete very old unread notifications
        unread_count = Notification.objects.filter(
            is_read=False,
            created_at__lt=unread_cutoff_date,
        ).delete()[0]

        logger.info(
            f"Cleaned {read_count} old read notifications and "
            f"{unread_count} old unread notifications"
        )
        return True

    except Exception as e:
        logger.error(f"Error cleaning old notifications: {e}")
        return False


@shared_task(base=RetryableTask)
def clean_inactive_device_tokens():
    """
    Clean inactive device tokens.
    """
    try:
        # Define retention period (e.g., keep inactive tokens for 30 days)
        from apps.notifications.services import DeviceTokenService
        count = DeviceTokenService.clean_inactive_tokens(days=30)

        logger.info(f"Cleaned {count} inactive device tokens")
        return True

    except Exception as e:
        logger.error(f"Error cleaning inactive device tokens: {e}")
        return False