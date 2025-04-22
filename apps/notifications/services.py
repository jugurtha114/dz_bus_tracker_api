import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.db import transaction

from apps.core.constants import NOTIFICATION_TYPES
from apps.core.exceptions import ValidationError, ObjectNotFound
from .models import Notification, NotificationPreference, PushToken, NotificationLog


logger = logging.getLogger(__name__)


def create_notification(user, notification_type, title, message, data=None, 
                       is_action_required=False, action_url='', expiration_date=None,
                       send_push=True, send_email=False, send_sms=False):
    if notification_type not in dict(NOTIFICATION_TYPES):
        raise ValidationError(f"Invalid notification type: {notification_type}")
    
    # Create notification
    notification = Notification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
        data=data or {},
        is_action_required=is_action_required,
        action_url=action_url,
        expiration_date=expiration_date,
        sent_via_push=False,
        sent_via_email=False,
        sent_via_sms=False
    )
    
    # Get user's notification preferences
    preferences = get_or_create_notification_preferences(user, notification_type)
    
    # Send notifications based on preferences and requested channels
    if send_push and preferences.push_enabled:
        success = send_push_notification(user, title, message, data)
        if success:
            notification.sent_via_push = True
    
    if send_email and preferences.email_enabled:
        success = send_email_notification(user.email, title, message)
        if success:
            notification.sent_via_email = True
    
    if send_sms and preferences.sms_enabled and user.phone_number:
        success = send_sms_notification(user.phone_number, message)
        if success:
            notification.sent_via_sms = True
    
    # Save notification with updated sent statuses
    notification.save()
    
    return notification


def send_notification(user, notification_type, title, message, data=None,
                     is_action_required=False, action_url=''):
    return create_notification(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
        is_action_required=is_action_required,
        action_url=action_url,
        send_push=True,
        send_email=False,
        send_sms=False
    )


def send_push_notification(user, title, message, data=None):
    tokens = PushToken.objects.filter(user=user, is_active=True)
    
    if not tokens.exists():
        return None
    
    fcm_tokens = [token.token for token in tokens]
    
    try:
        # Firebase Cloud Messaging
        import firebase_admin
        from firebase_admin import credentials, messaging
        
        # Initialize Firebase if not already initialized
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
                firebase_admin.initialize_app(cred)
            except (ValueError, FileNotFoundError) as e:
                logger.error(f"Failed to initialize Firebase: {str(e)}")
                return None
        
        # Create message
        message_data = {
            'title': title,
            'body': message,
            'data': data or {},
        }
        
        # Send message to all tokens
        responses = []
        for token in fcm_tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=message
                    ),
                    data=data or {},
                    token=token
                )
                
                response = messaging.send(message)
                responses.append(response)
                
                # Log success
                log_notification(
                    notification=notification,
                    method='push',
                    success=True,
                    provider_response={'message_id': response}
                )
            except Exception as e:
                # Log error
                log_notification(
                    notification=notification,
                    method='push',
                    success=False,
                    error_message=str(e)
                )
        
        return responses[0] if responses else None
    
    except Exception as e:
        logger.error(f"Failed to send push notification: {str(e)}")
        
        # Log error
        log_notification(
            notification=notification,
            method='push',
            success=False,
            error_message=str(e)
        )
        
        return None


def send_email_notification(to_email, subject, message, html_message=None):
    try:
        # If no HTML message provided, create a simple one
        if not html_message:
            html_message = render_to_string(
                'emails/notification.html',
                {
                    'title': subject,
                    'message': message
                }
            )
        
        # Send email
        sent = send_mail(
            subject=subject,
            message=message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False
        )
        
        # Log result
        log_notification(
            notification=notification,
            method='email',
            success=sent > 0
        )
        
        return sent > 0
    
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        
        # Log error
        log_notification(
            notification=notification,
            method='email',
            success=False,
            error_message=str(e)
        )
        
        return False


def send_sms_notification(phone_number, message):
    try:
        # Twilio integration
        from twilio.rest import Client
        
        # Check if Twilio credentials are available
        if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER):
            logger.error("Twilio credentials not configured")
            return False
        
        # Initialize Twilio client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Send SMS
        sms = client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=str(phone_number)
        )
        
        # Log success
        log_notification(
            notification=notification,
            method='sms',
            success=True,
            provider_response={'sid': sms.sid}
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to send SMS notification: {str(e)}")
        
        # Log error
        log_notification(
            notification=notification,
            method='sms',
            success=False,
            error_message=str(e)
        )
        
        return False


def log_notification(notification, method, success, error_message=None, provider_response=None):
    try:
        # Create log entry
        NotificationLog.objects.create(
            notification=notification,
            method=method,
            success=success,
            error_message=error_message or '',
            provider_response=provider_response or {}
        )
        
        return True
    except Exception as e:
        logger.error(f"Failed to log notification: {str(e)}")
        return False


def mark_notification_as_read(notification_id):
    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        raise ObjectNotFound("Notification not found")
    
    # Mark as read
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    
    return notification


def mark_notifications_as_read(notification_ids):
    # Mark multiple notifications as read
    updated_count = Notification.objects.filter(
        id__in=notification_ids,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )
    
    return updated_count


def mark_all_as_read(user_id):
    # Mark all notifications for a user as read
    updated_count = Notification.objects.filter(
        user_id=user_id,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )
    
    return updated_count


def get_or_create_notification_preferences(user, notification_type):
    # Get or create notification preferences for a user and type
    preference, created = NotificationPreference.objects.get_or_create(
        user=user,
        notification_type=notification_type,
        defaults={
            'push_enabled': True,
            'email_enabled': user.is_email_verified,
            'sms_enabled': user.is_phone_verified
        }
    )
    
    return preference


def update_notification_preferences(user_id, notification_type, preferences):
    try:
        preference = NotificationPreference.objects.get(
            user_id=user_id,
            notification_type=notification_type
        )
    except NotificationPreference.DoesNotExist:
        # Create if not exists
        preference = get_or_create_notification_preferences(
            user_id=user_id,
            notification_type=notification_type
        )
    
    # Update preferences
    for field, value in preferences.items():
        if hasattr(preference, field):
            setattr(preference, field, value)
    
    preference.save()
    
    return preference


def register_push_token(user, token, device_type, device_name=''):
    # Register or update a push token
    push_token, created = PushToken.objects.update_or_create(
        user=user,
        token=token,
        defaults={
            'device_type': device_type,
            'device_name': device_name,
            'is_active': True
        }
    )
    
    return push_token


def deactivate_push_token(token):
    try:
        push_token = PushToken.objects.get(token=token)
    except PushToken.DoesNotExist:
        raise ObjectNotFound("Push token not found")
    
    # Deactivate token
    push_token.is_active = False
    push_token.save(update_fields=['is_active'])
    
    return push_token


def cleanup_expired_notifications(days=30):
    # Delete expired notifications
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete notifications with expiration date in the past
    expired_by_date_count = Notification.objects.filter(
        expiration_date__lt=timezone.now()
    ).delete()[0]
    
    # Delete old read notifications
    old_read_count = Notification.objects.filter(
        is_read=True,
        read_at__lt=cutoff_date
    ).delete()[0]
    
    return {
        'expired_by_date_count': expired_by_date_count,
        'old_read_count': old_read_count
    }


def create_bulk_notifications(user_ids, notification_type, title, message, 
                             data=None, is_action_required=False, action_url='',
                             expiration_date=None, send_push=True, 
                             send_email=False, send_sms=False):
    from apps.authentication.models import User
    
    # Get users
    users = User.objects.filter(id__in=user_ids, is_active=True)
    
    created_count = 0
    
    # Create notifications in bulk
    with transaction.atomic():
        for user in users:
            try:
                notification = create_notification(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data=data,
                    is_action_required=is_action_required,
                    action_url=action_url,
                    expiration_date=expiration_date,
                    send_push=send_push,
                    send_email=send_email,
                    send_sms=send_sms
                )
                
                if notification:
                    created_count += 1
            except Exception as e:
                logger.error(f"Failed to create notification for user {user.id}: {str(e)}")
    
    return created_count
