"""
Enhanced notification services with professional push notification support.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from dataclasses import asdict

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from celery import shared_task

from apps.accounts.selectors import get_user_by_id
from apps.core.constants import (
    NOTIFICATION_CHANNEL_PUSH,
    NOTIFICATION_CHANNEL_EMAIL,
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_CHANNEL_IN_APP,
)
from apps.core.exceptions import ValidationError

from .firebase import (
    FCMService, 
    FCMNotificationData, 
    FCMDataPayload, 
    FCMPriority,
    FCMResult
)
from .templates import NotificationTemplateFactory
from .models import (
    DeviceToken, 
    Notification, 
    NotificationPreference, 
    NotificationSchedule
)
from .selectors import get_user_device_tokens, get_notification_by_id

logger = logging.getLogger(__name__)


class EnhancedDeviceTokenService:
    """Enhanced device token management service."""
    
    # Cache configuration
    CACHE_KEY_TOKEN_VALIDATION = "device_token:validation:{}"
    CACHE_KEY_USER_TOKENS = "device_token:user:{}"
    CACHE_TTL = 3600  # 1 hour
    
    @classmethod
    @transaction.atomic
    def register_device_token(
        cls,
        user_id: str,
        token: str,
        device_type: str,
        device_info: Optional[Dict[str, Any]] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None
    ) -> DeviceToken:
        """
        Register or update a device token with enhanced validation.
        
        Args:
            user_id: ID of the user
            token: FCM registration token
            device_type: Type of device (ios, android, web)
            device_info: Additional device information
            app_version: Application version
            os_version: Operating system version
            
        Returns:
            DeviceToken object
        """
        try:
            user = get_user_by_id(user_id)
            
            # Validate token format
            if not cls._validate_token_format(token):
                raise ValidationError("Invalid token format")
            
            # Test token with FCM
            if not cls._test_token_with_fcm(token):
                logger.warning(f"Token validation failed with FCM: {token[:20]}...")
                raise ValidationError("Token validation failed")
            
            # Get or create device token
            device_token, created = DeviceToken.objects.get_or_create(
                user=user,
                token=token,
                defaults={
                    'device_type': device_type,
                    'is_active': True,
                }
            )
            
            # Update token information
            if not created:
                device_token.device_type = device_type
                device_token.is_active = True
                device_token.last_used = timezone.now()
                device_token.save()
            
            # Store additional device info in cache
            if device_info or app_version or os_version:
                info = {
                    'device_info': device_info or {},
                    'app_version': app_version,
                    'os_version': os_version,
                    'registered_at': timezone.now().isoformat()
                }
                cache.set(
                    cls.CACHE_KEY_TOKEN_VALIDATION.format(token),
                    info,
                    cls.CACHE_TTL
                )
            
            # Clear user tokens cache
            cache.delete(cls.CACHE_KEY_USER_TOKENS.format(user_id))
            
            logger.info(
                f"Device token {'registered' if created else 'updated'} "
                f"for user {user.email} ({device_type})"
            )
            
            return device_token
            
        except Exception as e:
            logger.error(f"Error registering device token: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def get_user_active_tokens(cls, user_id: str) -> List[DeviceToken]:
        """
        Get active device tokens for a user with caching.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of active DeviceToken objects
        """
        cache_key = cls.CACHE_KEY_USER_TOKENS.format(user_id)
        cached_tokens = cache.get(cache_key)
        
        if cached_tokens is not None:
            return cached_tokens
        
        tokens = list(DeviceToken.objects.filter(
            user_id=user_id,
            is_active=True
        ).select_related('user'))
        
        cache.set(cache_key, tokens, cls.CACHE_TTL)
        return tokens
    
    @classmethod
    @transaction.atomic
    def cleanup_invalid_tokens(cls, batch_size: int = 100) -> int:
        """
        Clean up invalid tokens identified by FCM.
        
        Args:
            batch_size: Number of tokens to process per batch
            
        Returns:
            Number of tokens cleaned up
        """
        try:
            # Get FCM invalid tokens from cache
            invalid_tokens = cache.get(FCMService.CACHE_KEY_INVALID_TOKENS, set())
            
            if not invalid_tokens:
                return 0
            
            # Process in batches
            cleaned_count = 0
            for i in range(0, len(invalid_tokens), batch_size):
                batch_tokens = list(invalid_tokens)[i:i + batch_size]
                
                # Deactivate tokens
                updated = DeviceToken.objects.filter(
                    token__in=batch_tokens,
                    is_active=True
                ).update(
                    is_active=False,
                    updated_at=timezone.now()
                )
                
                cleaned_count += updated
                
                # Clear cache for affected users
                affected_tokens = DeviceToken.objects.filter(
                    token__in=batch_tokens
                ).select_related('user')
                
                for token in affected_tokens:
                    cache.delete(cls.CACHE_KEY_USER_TOKENS.format(str(token.user.id)))
            
            logger.info(f"Cleaned up {cleaned_count} invalid device tokens")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up invalid tokens: {e}")
            return 0
    
    @classmethod
    def _validate_token_format(cls, token: str) -> bool:
        """Validate FCM token format."""
        if not token or not isinstance(token, str):
            return False
        
        # Basic FCM token validation
        return len(token) > 50 and ':' in token
    
    @classmethod
    def _test_token_with_fcm(cls, token: str) -> bool:
        """Test token validity with FCM (cached)."""
        cache_key = cls.CACHE_KEY_TOKEN_VALIDATION.format(token)
        cached_result = cache.get(cache_key)
        
        if cached_result is not None:
            return cached_result.get('valid', False)
        
        # For production, we'd do a dry-run send to test the token
        # For now, we'll use basic format validation
        try:
            if not FCMService.initialize():
                return True  # Assume valid if FCM not configured
            
            # TODO: Implement dry-run token validation
            # This would require sending a test message to FCM
            result = True
            
            cache.set(
                cache_key,
                {'valid': result, 'tested_at': timezone.now().isoformat()},
                cls.CACHE_TTL
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False


class EnhancedNotificationService:
    """Enhanced notification service with professional push notification support."""
    
    @classmethod
    @transaction.atomic
    def send_notification(
        cls,
        user_id: str,
        template_type: str,
        channels: Optional[List[str]] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        **template_kwargs
    ) -> Dict[str, Any]:
        """
        Send notification using template with multiple channels.
        
        Args:
            user_id: ID of the user
            template_type: Type of notification template
            channels: List of channels to send through
            priority: FCM message priority
            **template_kwargs: Arguments for the template
            
        Returns:
            Dictionary with send results for each channel
        """
        try:
            user = get_user_by_id(user_id)
            
            # Get notification template
            template = NotificationTemplateFactory.get_template(template_type)
            if not template:
                raise ValidationError(f"Unknown template type: {template_type}")
            
            # Get user preferences
            preference = NotificationPreference.objects.filter(
                user=user,
                notification_type=template_type,
                enabled=True
            ).first()
            
            # Determine channels to use
            if channels is None:
                if preference and preference.channels:
                    channels = preference.channels
                else:
                    channels = [NOTIFICATION_CHANNEL_IN_APP]
            
            # Check quiet hours
            if preference and cls._is_quiet_hours(preference):
                logger.info(f"Skipping notification for user {user.email} - quiet hours")
                return {'skipped': True, 'reason': 'quiet_hours'}
            
            # Create in-app notification
            notification = cls._create_in_app_notification(
                user=user,
                template=template,
                template_type=template_type,
                **template_kwargs
            )
            
            # Send through requested channels
            results = {}
            
            for channel in channels:
                if channel == NOTIFICATION_CHANNEL_PUSH:
                    results[channel] = cls._send_push_notification(
                        user=user,
                        template=template,
                        priority=priority,
                        **template_kwargs
                    )
                elif channel == NOTIFICATION_CHANNEL_EMAIL:
                    results[channel] = cls._send_email_notification(
                        user=user,
                        notification=notification
                    )
                elif channel == NOTIFICATION_CHANNEL_SMS:
                    results[channel] = cls._send_sms_notification(
                        user=user,
                        notification=notification
                    )
                elif channel == NOTIFICATION_CHANNEL_IN_APP:
                    results[channel] = {'success': True, 'message': 'In-app notification created'}
            
            logger.info(
                f"Sent {template_type} notification to user {user.email} "
                f"via channels: {', '.join(channels)}"
            )
            
            return {
                'success': True,
                'notification_id': str(notification.id),
                'channels': results
            }
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def send_bulk_notification(
        cls,
        user_ids: List[str],
        template_type: str,
        channels: Optional[List[str]] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        **template_kwargs
    ) -> Dict[str, Any]:
        """
        Send notification to multiple users efficiently.
        
        Args:
            user_ids: List of user IDs
            template_type: Type of notification template
            channels: List of channels to send through
            priority: FCM message priority
            **template_kwargs: Arguments for the template
            
        Returns:
            Dictionary with bulk send results
        """
        # Use Celery task for bulk operations
        task = send_bulk_notification_task.delay(
            user_ids=user_ids,
            template_type=template_type,
            channels=channels or [NOTIFICATION_CHANNEL_IN_APP],
            priority=priority.value,
            **template_kwargs
        )
        
        return {
            'success': True,
            'task_id': task.id,
            'user_count': len(user_ids)
        }
    
    @classmethod
    def _create_in_app_notification(
        cls,
        user,
        template,
        template_type: str,
        **template_kwargs
    ) -> Notification:
        """Create in-app notification record."""
        notification = Notification.objects.create(
            user=user,
            notification_type=template_type,
            title=template.get_title(**template_kwargs),
            message=template.get_body(**template_kwargs),
            channel=NOTIFICATION_CHANNEL_IN_APP,
            data=template_kwargs
        )
        
        return notification
    
    @classmethod
    def _send_push_notification(
        cls,
        user,
        template,
        priority: FCMPriority = FCMPriority.NORMAL,
        **template_kwargs
    ) -> Dict[str, Any]:
        """Send push notification via FCM."""
        try:
            # Get user's device tokens
            tokens = EnhancedDeviceTokenService.get_user_active_tokens(str(user.id))
            
            if not tokens:
                logger.warning(f"No device tokens found for user {user.email}")
                return {'success': False, 'error': 'No device tokens'}
            
            # Build notification data
            notification_data = template.build_notification(**template_kwargs)
            data_payload = template.get_data_payload(**template_kwargs)
            
            # Send to multiple tokens
            token_strings = [token.token for token in tokens]
            result = FCMService.send_multicast(
                tokens=token_strings,
                notification=notification_data,
                data_payload=data_payload,
                priority=priority
            )
            
            # Handle invalid tokens
            if result.invalid_tokens:
                DeviceToken.objects.filter(
                    token__in=result.invalid_tokens
                ).update(is_active=False)
                
                # Clear cache
                cache.delete(
                    EnhancedDeviceTokenService.CACHE_KEY_USER_TOKENS.format(str(user.id))
                )
            
            return {
                'success': result.success,
                'success_count': result.success_count,
                'failure_count': result.failure_count,
                'invalid_tokens': len(result.invalid_tokens)
            }
            
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def _send_email_notification(cls, user, notification) -> Dict[str, Any]:
        """Send email notification."""
        try:
            # Check if user has email notifications enabled
            if hasattr(user, 'profile') and not user.profile.email_notifications_enabled:
                return {'success': False, 'error': 'Email notifications disabled'}
            
            # Import email modules
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            
            # Render email content
            context = {
                'notification': notification,
                'user': user,
                'app_name': getattr(settings, 'APP_NAME', 'DZ Bus Tracker')
            }
            
            try:
                html_content = render_to_string('notifications/email.html', context)
                text_content = render_to_string('notifications/email.txt', context)
            except Exception:
                # Fallback to simple text email
                html_content = None
                text_content = f"{notification.title}\n\n{notification.message}"
            
            # Send email
            send_mail(
                subject=notification.title,
                message=text_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@dzbustracker.com'),
                recipient_list=[user.email],
                html_message=html_content,
                fail_silently=False
            )
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def _send_sms_notification(cls, user, notification) -> Dict[str, Any]:
        """Send SMS notification."""
        try:
            # Check if user has SMS notifications enabled
            if hasattr(user, 'profile') and not user.profile.sms_notifications_enabled:
                return {'success': False, 'error': 'SMS notifications disabled'}
            
            # Check if Twilio is configured
            if not all([
                getattr(settings, "TWILIO_ACCOUNT_SID", None),
                getattr(settings, "TWILIO_AUTH_TOKEN", None),
                getattr(settings, "TWILIO_PHONE_NUMBER", None),
            ]):
                return {'success': False, 'error': 'SMS not configured'}
            
            # Check if user has phone number
            if not user.phone_number:
                return {'success': False, 'error': 'No phone number'}
            
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
                to=user.phone_number,
            )
            
            return {'success': True, 'message_sid': message.sid}
            
        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def _is_quiet_hours(cls, preference: NotificationPreference) -> bool:
        """Check if current time is within quiet hours."""
        if not preference.quiet_hours_start or not preference.quiet_hours_end:
            return False
        
        now = timezone.now().time()
        start = preference.quiet_hours_start
        end = preference.quiet_hours_end
        
        # Handle overnight quiet hours
        if start > end:
            return now >= start or now <= end
        else:
            return start <= now <= end


# Celery tasks for background processing
@shared_task(name='notifications.send_bulk_notification')
def send_bulk_notification_task(
    user_ids: List[str],
    template_type: str,
    channels: List[str],
    priority: str = 'normal',
    **template_kwargs
) -> Dict[str, Any]:
    """
    Celery task for sending bulk notifications.
    """
    try:
        priority_enum = FCMPriority.HIGH if priority == 'high' else FCMPriority.NORMAL
        
        # Process users in batches
        batch_size = 100
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
                        
                except Exception as e:
                    logger.error(f"Failed to send notification to user {user_id}: {e}")
                    total_failed += 1
        
        logger.info(
            f"Bulk notification completed: {total_sent} sent, {total_failed} failed"
        )
        
        return {
            'success': True,
            'total_sent': total_sent,
            'total_failed': total_failed
        }
        
    except Exception as e:
        logger.error(f"Bulk notification task failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='notifications.cleanup_invalid_tokens')
def cleanup_invalid_tokens_task() -> Dict[str, Any]:
    """
    Celery task for cleaning up invalid device tokens.
    """
    try:
        cleaned_count = EnhancedDeviceTokenService.cleanup_invalid_tokens()
        return {'success': True, 'cleaned_count': cleaned_count}
    except Exception as e:
        logger.error(f"Token cleanup task failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='notifications.process_scheduled_notifications')
def process_scheduled_notifications_task() -> Dict[str, Any]:
    """
    Celery task for processing scheduled notifications.
    """
    try:
        # Get due notifications
        due_notifications = NotificationSchedule.objects.filter(
            is_sent=False,
            scheduled_for__lte=timezone.now()
        ).select_related('user')
        
        processed_count = 0
        failed_count = 0
        
        for scheduled in due_notifications:
            try:
                # Send notification
                result = EnhancedNotificationService.send_notification(
                    user_id=str(scheduled.user.id),
                    template_type=scheduled.notification_type,
                    channels=scheduled.channels,
                    **scheduled.data
                )
                
                # Mark as sent
                scheduled.is_sent = True
                scheduled.sent_at = timezone.now()
                
                if not result.get('success'):
                    scheduled.error = result.get('error', 'Unknown error')
                
                scheduled.save()
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process scheduled notification {scheduled.id}: {e}")
                scheduled.error = str(e)
                scheduled.save()
                failed_count += 1
        
        logger.info(
            f"Processed scheduled notifications: {processed_count} sent, {failed_count} failed"
        )
        
        return {
            'success': True,
            'processed_count': processed_count,
            'failed_count': failed_count
        }
        
    except Exception as e:
        logger.error(f"Scheduled notifications task failed: {e}")
        return {'success': False, 'error': str(e)}