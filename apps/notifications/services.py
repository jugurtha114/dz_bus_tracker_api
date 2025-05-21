"""
Service functions for the notifications app.
"""
import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.selectors import get_user_by_id
from apps.core.constants import (
    NOTIFICATION_CHANNEL_EMAIL,
    NOTIFICATION_CHANNEL_IN_APP,
    NOTIFICATION_CHANNEL_PUSH,
    NOTIFICATION_CHANNEL_SMS,
)
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object

from .models import DeviceToken, Notification
from .selectors import get_notification_by_id, get_user_device_tokens, user_has_device_token

logger = logging.getLogger(__name__)


class NotificationService(BaseService):
    """
    Service for notification-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_notification(cls, user_id, notification_type, title, message,
                            channel=NOTIFICATION_CHANNEL_IN_APP, data=None):
        """
        Create a notification for a user.

        Args:
            user_id: ID of the user
            notification_type: Type of notification
            title: Title of the notification
            message: Message of the notification
            channel: Channel to send the notification through
            data: Additional data for the notification

        Returns:
            Created Notification object
        """
        try:
            # Get user
            user = get_user_by_id(user_id)

            # Validate inputs
            if not notification_type:
                raise ValidationError("Notification type is required.")

            if not title:
                raise ValidationError("Title is required.")

            if not message:
                raise ValidationError("Message is required.")

            # Create notification
            notification_data = {
                "user": user,
                "notification_type": notification_type,
                "title": title,
                "message": message,
                "channel": channel,
                "data": data or {},
            }

            notification = create_object(Notification, notification_data)

            # Send notification through appropriate channel
            if channel == NOTIFICATION_CHANNEL_PUSH:
                cls.send_push_notification(notification)
            elif channel == NOTIFICATION_CHANNEL_EMAIL:
                cls.send_email_notification(notification)
            elif channel == NOTIFICATION_CHANNEL_SMS:
                cls.send_sms_notification(notification)

            logger.info(
                f"Created {notification_type} notification for user {user.email} "
                f"via {channel} channel"
            )
            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def mark_as_read(cls, notification_id):
        """
        Mark a notification as read.

        Args:
            notification_id: ID of the notification

        Returns:
            Updated Notification object
        """
        try:
            # Get notification
            notification = get_notification_by_id(notification_id)

            # Check if already read
            if notification.is_read:
                return notification

            # Mark as read
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])

            logger.info(f"Marked notification {notification.id} as read")
            return notification

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def mark_all_as_read(cls, user_id):
        """
        Mark all notifications for a user as read.

        Args:
            user_id: ID of the user

        Returns:
            Number of notifications marked as read
        """
        try:
            # Get user
            user = get_user_by_id(user_id)

            # Mark all as read
            count = Notification.objects.filter(
                user=user,
                is_read=False
            ).update(
                is_read=True,
                read_at=timezone.now(),
                updated_at=timezone.now(),
            )

            logger.info(f"Marked {count} notifications as read for user {user.email}")
            return count

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            raise ValidationError(str(e))

    @classmethod
    def send_push_notification(cls, notification):
        """
        Send a push notification.

        Args:
            notification: Notification object

        Returns:
            Boolean indicating success
        """
        try:
            # Check if Firebase credentials are configured
            if not getattr(settings, "FIREBASE_CREDENTIALS_PATH", None):
                logger.warning("Firebase credentials not configured, skipping push notification")
                return False

            # Get user's device tokens
            tokens = get_user_device_tokens(notification.user.id)

            if not tokens:
                logger.warning(f"No device tokens found for user {notification.user.email}")
                return False

            # Import Firebase admin
            import firebase_admin
            from firebase_admin import credentials, messaging

            # Initialize Firebase admin if not already initialized
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)

            # Prepare message
            message = messaging.MulticastMessage(
                tokens=[token.token for token in tokens],
                notification=messaging.Notification(
                    title=notification.title,
                    body=notification.message,
                ),
                data=notification.data,
            )

            # Send message
            response = messaging.send_multicast(message)

            logger.info(
                f"Sent push notification to {len(tokens)} devices for user "
                f"{notification.user.email}: {response.success_count} succeeded, "
                f"{response.failure_count} failed"
            )

            return response.success_count > 0

        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False

    @classmethod
    def send_email_notification(cls, notification):
        """
        Send an email notification.

        Args:
            notification: Notification object

        Returns:
            Boolean indicating success
        """
        try:
            # Check if user has email
            if not notification.user.email:
                logger.warning(f"No email address found for user {notification.user.id}")
                return False

            # Check if user's profile allows email notifications
            if (hasattr(notification.user, "profile") and
                    not notification.user.profile.email_notifications_enabled):
                logger.info(f"Email notifications disabled for user {notification.user.email}")
                return False

            # Import email modules
            from django.core.mail import send_mail
            from django.template.loader import render_to_string

            # Render email content
            context = {
                "notification": notification,
                "user": notification.user,
            }

            html_content = render_to_string("notifications/email.html", context)
            text_content = render_to_string("notifications/email.txt", context)

            # Send email
            send_mail(
                subject=notification.title,
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                html_message=html_content,
            )

            logger.info(f"Sent email notification to {notification.user.email}")
            return True

        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False

    @classmethod
    def send_sms_notification(cls, notification):
        """
        Send an SMS notification.

        Args:
            notification: Notification object

        Returns:
            Boolean indicating success
        """
        try:
            # Check if Twilio credentials are configured
            if not all([
                getattr(settings, "TWILIO_ACCOUNT_SID", None),
                getattr(settings, "TWILIO_AUTH_TOKEN", None),
                getattr(settings, "TWILIO_PHONE_NUMBER", None),
            ]):
                logger.warning("Twilio credentials not configured, skipping SMS notification")
                return False

            # Check if user has phone number
            if not notification.user.phone_number:
                logger.warning(f"No phone number found for user {notification.user.email}")
                return False

            # Check if user's profile allows SMS notifications
            if (hasattr(notification.user, "profile") and
                    not notification.user.profile.sms_notifications_enabled):
                logger.info(f"SMS notifications disabled for user {notification.user.email}")
                return False

            # Import Twilio client
            from twilio.rest import Client

            # Initialize Twilio client
            client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )

            # Send SMS
            message = client.messages.create(
                body=f"{notification.title}: {notification.message}",
                from_=settings.TWILIO_PHONE_NUMBER,
                to=notification.user.phone_number,
            )

            logger.info(f"Sent SMS notification to {notification.user.phone_number}")
            return True

        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}")
            return False


class DeviceTokenService(BaseService):
    """
    Service for device token-related operations.
    """

    @classmethod
    @transaction.atomic
    def register_device(cls, user_id, token, device_type):
        """
        Register a device token for a user.

        Args:
            user_id: ID of the user
            token: Device token
            device_type: Type of device

        Returns:
            Created or updated DeviceToken object
        """
        try:
            # Get user
            user = get_user_by_id(user_id)

            # Validate inputs
            if not token:
                raise ValidationError("Device token is required.")

            if not device_type:
                raise ValidationError("Device type is required.")

            # Check if token already exists
            if user_has_device_token(user_id, token):
                # Update existing token
                device_token = DeviceToken.objects.get(
                    user=user,
                    token=token,
                )

                device_token.device_type = device_type
                device_token.is_active = True
                device_token.save(update_fields=[
                    "device_type",
                    "is_active",
                    "last_used",
                    "updated_at",
                ])

                logger.info(f"Updated device token for user {user.email}")
                return device_token

            # Create new token
            device_token_data = {
                "user": user,
                "token": token,
                "device_type": device_type,
                "is_active": True,
            }

            device_token = create_object(DeviceToken, device_token_data)

            logger.info(f"Registered device token for user {user.email}")
            return device_token

        except Exception as e:
            logger.error(f"Error registering device token: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_device(cls, user_id, token):
        """
        Deactivate a device token for a user.

        Args:
            user_id: ID of the user
            token: Device token

        Returns:
            Deactivated DeviceToken object
        """
        try:
            # Get user
            user = get_user_by_id(user_id)

            # Validate inputs
            if not token:
                raise ValidationError("Device token is required.")

            # Get device token
            try:
                device_token = DeviceToken.objects.get(
                    user=user,
                    token=token,
                )
            except DeviceToken.DoesNotExist:
                raise ValidationError("Device token not found.")

            # Deactivate token
            device_token.is_active = False
            device_token.save(update_fields=["is_active", "updated_at"])

            logger.info(f"Deactivated device token for user {user.email}")
            return device_token

        except Exception as e:
            logger.error(f"Error deactivating device token: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def clean_inactive_tokens(cls, days=30):
        """
        Clean inactive tokens older than a certain number of days.

        Args:
            days: Number of days to keep inactive tokens

        Returns:
            Number of tokens deleted
        """
        try:
            # Calculate cutoff date
            cutoff_date = timezone.now() - timezone.timedelta(days=days)

            # Delete inactive tokens
            count, _ = DeviceToken.objects.filter(
                is_active=False,
                updated_at__lt=cutoff_date,
            ).delete()

            logger.info(f"Cleaned {count} inactive device tokens")
            return count

        except Exception as e:
            logger.error(f"Error cleaning inactive tokens: {e}")
            raise ValidationError(str(e))