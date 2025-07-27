"""
Professional Firebase Cloud Messaging (FCM) service implementation.
This module provides robust push notification functionality with best practices.
"""
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from functools import wraps

import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class FCMPriority(Enum):
    """FCM message priority levels."""
    NORMAL = "normal"
    HIGH = "high"


class FCMColor(Enum):
    """Predefined notification colors."""
    DEFAULT = "#2196F3"
    SUCCESS = "#4CAF50"
    WARNING = "#FF9800"
    ERROR = "#F44336"
    INFO = "#00BCD4"


@dataclass
class FCMNotificationData:
    """Data structure for FCM notifications."""
    title: str
    body: str
    icon: Optional[str] = None
    image: Optional[str] = None
    sound: Optional[str] = "default"
    badge: Optional[int] = None
    tag: Optional[str] = None
    color: Optional[str] = FCMColor.DEFAULT.value
    click_action: Optional[str] = None
    channel_id: Optional[str] = "default"


@dataclass
class FCMDataPayload:
    """Data payload for FCM messages."""
    action: Optional[str] = None
    screen: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class FCMResult:
    """Result of FCM operation."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    failure_count: int = 0
    success_count: int = 0
    invalid_tokens: List[str] = None

    def __post_init__(self):
        if self.invalid_tokens is None:
            self.invalid_tokens = []


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying FCM operations on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for subsequent retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt <= max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt > max_retries:
                        logger.error(f"FCM operation failed after {max_retries} retries: {e}")
                        raise
                    
                    logger.warning(f"FCM operation failed (attempt {attempt}/{max_retries}): {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            return None
        return wrapper
    return decorator


class FCMService:
    """
    Professional Firebase Cloud Messaging service with best practices.
    """
    
    _app = None
    _initialized = False
    
    # Cache keys
    CACHE_KEY_INVALID_TOKENS = "fcm:invalid_tokens"
    CACHE_KEY_RATE_LIMIT = "fcm:rate_limit:{}"
    
    # Rate limiting
    MAX_MESSAGES_PER_MINUTE = 500
    BATCH_SIZE = 500
    
    @classmethod
    def initialize(cls) -> bool:
        """
        Initialize Firebase Admin SDK.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if cls._initialized:
            return True
        
        try:
            # Check if credentials are configured
            credentials_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
            if not credentials_path:
                # Try to find google-services.json in project root
                project_root = Path(settings.BASE_DIR)
                google_services_path = project_root / 'google-services.json'
                
                if google_services_path.exists():
                    # Extract server key from google-services.json
                    with open(google_services_path, 'r') as f:
                        google_services = json.load(f)
                        project_id = google_services['project_info']['project_id']
                        
                    # For server-side, we need the service account key
                    # This should be a separate file, not google-services.json
                    logger.warning(
                        "FIREBASE_CREDENTIALS_PATH not set and no service account key found. "
                        "Please obtain a service account key from Firebase Console."
                    )
                    return False
                else:
                    logger.error("Firebase credentials not found")
                    return False
            
            # Initialize Firebase Admin SDK
            if not firebase_admin._apps:
                cred = credentials.Certificate(credentials_path)
                cls._app = firebase_admin.initialize_app(cred)
            else:
                cls._app = firebase_admin.get_app()
            
            cls._initialized = True
            logger.info("Firebase Admin SDK initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
            return False
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if Firebase is initialized."""
        return cls._initialized
    
    @classmethod
    @retry_on_failure(max_retries=3)
    def send_notification(
        cls,
        token: str,
        notification: FCMNotificationData,
        data_payload: Optional[FCMDataPayload] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> FCMResult:
        """
        Send push notification to a single device.
        
        Args:
            token: FCM registration token
            notification: Notification data
            data_payload: Optional data payload
            priority: Message priority
            ttl: Time to live in seconds
            collapse_key: Collapse key for message grouping
            
        Returns:
            FCMResult object with operation result
        """
        if not cls.initialize():
            return FCMResult(success=False, error="Firebase not initialized")
        
        try:
            # Validate token
            if not cls._is_valid_token(token):
                return FCMResult(
                    success=False, 
                    error="Invalid token format",
                    invalid_tokens=[token]
                )
            
            # Check rate limiting
            if not cls._check_rate_limit():
                return FCMResult(success=False, error="Rate limit exceeded")
            
            # Build message
            message = cls._build_message(
                token=token,
                notification=notification,
                data_payload=data_payload,
                priority=priority,
                ttl=ttl,
                collapse_key=collapse_key
            )
            
            # Send message
            message_id = messaging.send(message)
            
            # Update rate limit counter
            cls._update_rate_limit()
            
            logger.info(f"FCM notification sent successfully: {message_id}")
            return FCMResult(
                success=True,
                message_id=message_id,
                success_count=1
            )
            
        except messaging.UnregisteredError:
            logger.warning(f"Invalid FCM token: {token}")
            cls._cache_invalid_token(token)
            return FCMResult(
                success=False,
                error="Unregistered token",
                invalid_tokens=[token]
            )
            
        except messaging.SenderIdMismatchError:
            logger.error(f"Sender ID mismatch for token: {token}")
            return FCMResult(
                success=False,
                error="Sender ID mismatch",
                invalid_tokens=[token]
            )
            
        except messaging.QuotaExceededError:
            logger.error("FCM quota exceeded")
            return FCMResult(success=False, error="Quota exceeded")
            
        except Exception as e:
            logger.error(f"Failed to send FCM notification: {e}")
            return FCMResult(success=False, error=str(e))
    
    @classmethod
    @retry_on_failure(max_retries=3)
    def send_multicast(
        cls,
        tokens: List[str],
        notification: FCMNotificationData,
        data_payload: Optional[FCMDataPayload] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> FCMResult:
        """
        Send push notification to multiple devices.
        
        Args:
            tokens: List of FCM registration tokens
            notification: Notification data
            data_payload: Optional data payload
            priority: Message priority
            ttl: Time to live in seconds
            collapse_key: Collapse key for message grouping
            
        Returns:
            FCMResult object with operation result
        """
        if not cls.initialize():
            return FCMResult(success=False, error="Firebase not initialized")
        
        if not tokens:
            return FCMResult(success=False, error="No tokens provided")
        
        try:
            # Filter out invalid tokens
            valid_tokens = [t for t in tokens if cls._is_valid_token(t)]
            if not valid_tokens:
                return FCMResult(
                    success=False,
                    error="No valid tokens",
                    invalid_tokens=tokens
                )
            
            # Check rate limiting
            if not cls._check_rate_limit(len(valid_tokens)):
                return FCMResult(success=False, error="Rate limit exceeded")
            
            # Process in batches
            all_results = []
            invalid_tokens = []
            
            for i in range(0, len(valid_tokens), cls.BATCH_SIZE):
                batch_tokens = valid_tokens[i:i + cls.BATCH_SIZE]
                
                # Build multicast message
                message = cls._build_multicast_message(
                    tokens=batch_tokens,
                    notification=notification,
                    data_payload=data_payload,
                    priority=priority,
                    ttl=ttl,
                    collapse_key=collapse_key
                )
                
                # Send batch
                response = messaging.send_multicast(message)
                all_results.append(response)
                
                # Handle failed tokens
                if response.failure_count > 0:
                    for idx, result in enumerate(response.responses):
                        if not result.success:
                            token = batch_tokens[idx]
                            error = result.exception
                            
                            if isinstance(error, messaging.UnregisteredError):
                                invalid_tokens.append(token)
                                cls._cache_invalid_token(token)
                            
                            logger.warning(f"Failed to send to token {token}: {error}")
            
            # Aggregate results
            total_success = sum(r.success_count for r in all_results)
            total_failure = sum(r.failure_count for r in all_results)
            
            # Update rate limit counter
            cls._update_rate_limit(total_success)
            
            logger.info(
                f"FCM multicast sent: {total_success} succeeded, "
                f"{total_failure} failed, {len(invalid_tokens)} invalid tokens"
            )
            
            return FCMResult(
                success=total_success > 0,
                success_count=total_success,
                failure_count=total_failure,
                invalid_tokens=invalid_tokens
            )
            
        except Exception as e:
            logger.error(f"Failed to send FCM multicast: {e}")
            return FCMResult(success=False, error=str(e))
    
    @classmethod
    def send_topic_notification(
        cls,
        topic: str,
        notification: FCMNotificationData,
        data_payload: Optional[FCMDataPayload] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        condition: Optional[str] = None
    ) -> FCMResult:
        """
        Send notification to a topic or condition.
        
        Args:
            topic: Topic name
            notification: Notification data
            data_payload: Optional data payload
            priority: Message priority
            condition: Optional condition for targeting
            
        Returns:
            FCMResult object with operation result
        """
        if not cls.initialize():
            return FCMResult(success=False, error="Firebase not initialized")
        
        try:
            # Build topic message
            message_data = {
                'notification': messaging.Notification(
                    title=notification.title,
                    body=notification.body,
                    image=notification.image
                ),
                'android': messaging.AndroidConfig(
                    priority=priority.value,
                    notification=messaging.AndroidNotification(
                        icon=notification.icon,
                        color=notification.color,
                        sound=notification.sound,
                        tag=notification.tag,
                        click_action=notification.click_action,
                        channel_id=notification.channel_id
                    )
                ),
                'apns': messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=notification.title,
                                body=notification.body
                            ),
                            badge=notification.badge,
                            sound=notification.sound
                        )
                    )
                ),
                'webpush': messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=notification.title,
                        body=notification.body,
                        icon=notification.icon,
                        image=notification.image,
                        badge=notification.badge,
                        tag=notification.tag
                    )
                )
            }
            
            # Add data payload if provided
            if data_payload:
                message_data['data'] = cls._serialize_data_payload(data_payload)
            
            # Create message with topic or condition
            if condition:
                message = messaging.Message(condition=condition, **message_data)
            else:
                message = messaging.Message(topic=topic, **message_data)
            
            # Send message
            message_id = messaging.send(message)
            
            logger.info(f"FCM topic notification sent: {message_id}")
            return FCMResult(success=True, message_id=message_id)
            
        except Exception as e:
            logger.error(f"Failed to send topic notification: {e}")
            return FCMResult(success=False, error=str(e))
    
    @classmethod
    def subscribe_to_topic(cls, tokens: List[str], topic: str) -> FCMResult:
        """
        Subscribe tokens to a topic.
        
        Args:
            tokens: List of FCM registration tokens
            topic: Topic name
            
        Returns:
            FCMResult object with operation result
        """
        if not cls.initialize():
            return FCMResult(success=False, error="Firebase not initialized")
        
        try:
            response = messaging.subscribe_to_topic(tokens, topic)
            
            logger.info(f"Subscribed {len(tokens)} tokens to topic '{topic}'")
            return FCMResult(
                success=response.success_count > 0,
                success_count=response.success_count,
                failure_count=response.failure_count
            )
            
        except Exception as e:
            logger.error(f"Failed to subscribe to topic: {e}")
            return FCMResult(success=False, error=str(e))
    
    @classmethod
    def unsubscribe_from_topic(cls, tokens: List[str], topic: str) -> FCMResult:
        """
        Unsubscribe tokens from a topic.
        
        Args:
            tokens: List of FCM registration tokens
            topic: Topic name
            
        Returns:
            FCMResult object with operation result
        """
        if not cls.initialize():
            return FCMResult(success=False, error="Firebase not initialized")
        
        try:
            response = messaging.unsubscribe_from_topic(tokens, topic)
            
            logger.info(f"Unsubscribed {len(tokens)} tokens from topic '{topic}'")
            return FCMResult(
                success=response.success_count > 0,
                success_count=response.success_count,
                failure_count=response.failure_count
            )
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from topic: {e}")
            return FCMResult(success=False, error=str(e))
    
    @classmethod
    def _build_message(
        cls,
        token: str,
        notification: FCMNotificationData,
        data_payload: Optional[FCMDataPayload] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> messaging.Message:
        """Build FCM message for single device."""
        message_data = {
            'token': token,
            'notification': messaging.Notification(
                title=notification.title,
                body=notification.body,
                image=notification.image
            ),
            'android': messaging.AndroidConfig(
                priority=priority.value,
                ttl=ttl,
                collapse_key=collapse_key,
                notification=messaging.AndroidNotification(
                    icon=notification.icon,
                    color=notification.color,
                    sound=notification.sound,
                    tag=notification.tag,
                    click_action=notification.click_action,
                    channel_id=notification.channel_id
                )
            ),
            'apns': messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=notification.title,
                            body=notification.body
                        ),
                        badge=notification.badge,
                        sound=notification.sound
                    )
                )
            ),
            'webpush': messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=notification.title,
                    body=notification.body,
                    icon=notification.icon,
                    image=notification.image,
                    badge=notification.badge,
                    tag=notification.tag
                )
            )
        }
        
        # Add data payload if provided
        if data_payload:
            message_data['data'] = cls._serialize_data_payload(data_payload)
        
        return messaging.Message(**message_data)
    
    @classmethod
    def _build_multicast_message(
        cls,
        tokens: List[str],
        notification: FCMNotificationData,
        data_payload: Optional[FCMDataPayload] = None,
        priority: FCMPriority = FCMPriority.NORMAL,
        ttl: Optional[int] = None,
        collapse_key: Optional[str] = None
    ) -> messaging.MulticastMessage:
        """Build FCM multicast message."""
        message_data = {
            'tokens': tokens,
            'notification': messaging.Notification(
                title=notification.title,
                body=notification.body,
                image=notification.image
            ),
            'android': messaging.AndroidConfig(
                priority=priority.value,
                ttl=ttl,
                collapse_key=collapse_key,
                notification=messaging.AndroidNotification(
                    icon=notification.icon,
                    color=notification.color,
                    sound=notification.sound,
                    tag=notification.tag,
                    click_action=notification.click_action,
                    channel_id=notification.channel_id
                )
            ),
            'apns': messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=notification.title,
                            body=notification.body
                        ),
                        badge=notification.badge,
                        sound=notification.sound
                    )
                )
            ),
            'webpush': messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=notification.title,
                    body=notification.body,
                    icon=notification.icon,
                    image=notification.image,
                    badge=notification.badge,
                    tag=notification.tag
                )
            )
        }
        
        # Add data payload if provided
        if data_payload:
            message_data['data'] = cls._serialize_data_payload(data_payload)
        
        return messaging.MulticastMessage(**message_data)
    
    @classmethod
    def _serialize_data_payload(cls, data_payload: FCMDataPayload) -> Dict[str, str]:
        """Serialize data payload to string values."""
        result = {}
        
        if data_payload.action:
            result['action'] = data_payload.action
        
        if data_payload.screen:
            result['screen'] = data_payload.screen
        
        if data_payload.data:
            # Convert all data values to strings
            for key, value in data_payload.data.items():
                if isinstance(value, (dict, list)):
                    result[key] = json.dumps(value)
                else:
                    result[key] = str(value)
        
        return result
    
    @classmethod
    def _is_valid_token(cls, token: str) -> bool:
        """Validate FCM token format."""
        if not token or not isinstance(token, str):
            return False
        
        # Check if token is in invalid tokens cache
        invalid_tokens = cache.get(cls.CACHE_KEY_INVALID_TOKENS, set())
        if token in invalid_tokens:
            return False
        
        # Basic format validation
        return len(token) > 10 and ':' in token
    
    @classmethod
    def _cache_invalid_token(cls, token: str):
        """Cache invalid token to avoid future attempts."""
        invalid_tokens = cache.get(cls.CACHE_KEY_INVALID_TOKENS, set())
        invalid_tokens.add(token)
        cache.set(cls.CACHE_KEY_INVALID_TOKENS, invalid_tokens, 3600)  # 1 hour
    
    @classmethod
    def _check_rate_limit(cls, count: int = 1) -> bool:
        """Check if we're within rate limits."""
        cache_key = cls.CACHE_KEY_RATE_LIMIT.format(
            timezone.now().strftime("%Y%m%d%H%M")
        )
        current_count = cache.get(cache_key, 0)
        
        return current_count + count <= cls.MAX_MESSAGES_PER_MINUTE
    
    @classmethod
    def _update_rate_limit(cls, count: int = 1):
        """Update rate limit counter."""
        cache_key = cls.CACHE_KEY_RATE_LIMIT.format(
            timezone.now().strftime("%Y%m%d%H%M")
        )
        current_count = cache.get(cache_key, 0)
        cache.set(cache_key, current_count + count, 60)  # 1 minute
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get FCM service statistics."""
        cache_key = cls.CACHE_KEY_RATE_LIMIT.format(
            timezone.now().strftime("%Y%m%d%H%M")
        )
        current_count = cache.get(cache_key, 0)
        invalid_tokens_count = len(cache.get(cls.CACHE_KEY_INVALID_TOKENS, set()))
        
        return {
            'initialized': cls._initialized,
            'current_minute_count': current_count,
            'rate_limit': cls.MAX_MESSAGES_PER_MINUTE,
            'invalid_tokens_cached': invalid_tokens_count,
            'batch_size': cls.BATCH_SIZE
        }