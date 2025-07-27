"""
Configuration for the enhanced notification system.
"""
from django.conf import settings

# Firebase Configuration
FIREBASE_CREDENTIALS_PATH = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
FIREBASE_PROJECT_ID = getattr(settings, 'FIREBASE_PROJECT_ID', None)

# FCM Configuration
FCM_MAX_BATCH_SIZE = getattr(settings, 'FCM_MAX_BATCH_SIZE', 500)
FCM_RATE_LIMIT_PER_MINUTE = getattr(settings, 'FCM_RATE_LIMIT_PER_MINUTE', 500)
FCM_RETRY_ATTEMPTS = getattr(settings, 'FCM_RETRY_ATTEMPTS', 3)
FCM_RETRY_DELAY = getattr(settings, 'FCM_RETRY_DELAY', 1.0)
FCM_RETRY_BACKOFF = getattr(settings, 'FCM_RETRY_BACKOFF', 2.0)

# Token Management
TOKEN_VALIDATION_CACHE_TTL = getattr(settings, 'TOKEN_VALIDATION_CACHE_TTL', 3600)  # 1 hour
TOKEN_CLEANUP_DAYS = getattr(settings, 'TOKEN_CLEANUP_DAYS', 90)
INVALID_TOKEN_CACHE_TTL = getattr(settings, 'INVALID_TOKEN_CACHE_TTL', 3600)  # 1 hour

# Notification Settings
DEFAULT_NOTIFICATION_CHANNELS = getattr(settings, 'DEFAULT_NOTIFICATION_CHANNELS', ['in_app'])
NOTIFICATION_BATCH_SIZE = getattr(settings, 'NOTIFICATION_BATCH_SIZE', 50)
NOTIFICATION_QUEUE_MAX_SIZE = getattr(settings, 'NOTIFICATION_QUEUE_MAX_SIZE', 1000)

# Monitoring
MONITORING_CACHE_TTL = getattr(settings, 'MONITORING_CACHE_TTL', 300)  # 5 minutes
HEALTH_CHECK_INTERVAL = getattr(settings, 'HEALTH_CHECK_INTERVAL', 300)  # 5 minutes
STATS_CACHE_TTL = getattr(settings, 'STATS_CACHE_TTL', 600)  # 10 minutes

# External Monitoring
NOTIFICATION_MONITORING_WEBHOOK = getattr(settings, 'NOTIFICATION_MONITORING_WEBHOOK', None)
SENTRY_NOTIFICATION_EVENTS = getattr(settings, 'SENTRY_NOTIFICATION_EVENTS', False)

# Email Settings
EMAIL_NOTIFICATION_ENABLED = getattr(settings, 'EMAIL_BACKEND', None) is not None
EMAIL_TEMPLATE_DIR = getattr(settings, 'EMAIL_TEMPLATE_DIR', 'notifications/email')

# SMS Settings
SMS_NOTIFICATION_ENABLED = all([
    getattr(settings, 'TWILIO_ACCOUNT_SID', None),
    getattr(settings, 'TWILIO_AUTH_TOKEN', None),
    getattr(settings, 'TWILIO_PHONE_NUMBER', None)
])

# Celery Task Settings
CELERY_TASK_ROUTES = {
    'notifications.send_bulk_notification': {'queue': 'notifications'},
    'notifications.process_scheduled_notifications': {'queue': 'notifications'},
    'notifications.cleanup_invalid_tokens': {'queue': 'maintenance'},
    'notifications.health_check': {'queue': 'monitoring'},
}

CELERY_BEAT_SCHEDULE = {
    'process-scheduled-notifications': {
        'task': 'notifications.process_scheduled_notifications',
        'schedule': 60.0,  # Every minute
    },
    'check-arrival-notifications': {
        'task': 'notifications.check_arrival_notifications',
        'schedule': 120.0,  # Every 2 minutes
    },
    'cleanup-invalid-tokens': {
        'task': 'notifications.cleanup_invalid_tokens',
        'schedule': 3600.0,  # Every hour
    },
    'notification-health-check': {
        'task': 'notifications.health_check',
        'schedule': 300.0,  # Every 5 minutes
    },
    'clean-old-notifications': {
        'task': 'notifications.clean_old_data',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days': 30}
    },
}

# Template Configuration
NOTIFICATION_TEMPLATES = {
    'bus_arrival': {
        'name': 'Bus Arrival',
        'description': 'Notifications when buses are approaching stops',
        'required_fields': ['bus_number', 'stop_name', 'minutes'],
        'optional_fields': ['bus_id', 'stop_id', 'line_id', 'estimated_arrival']
    },
    'bus_delay': {
        'name': 'Bus Delay',
        'description': 'Notifications about bus delays',
        'required_fields': ['bus_number', 'line_name', 'delay_minutes'],
        'optional_fields': ['reason', 'bus_id', 'line_id']
    },
    'trip_start': {
        'name': 'Trip Start',
        'description': 'Notifications when trips begin',
        'required_fields': ['bus_number', 'line_name'],
        'optional_fields': ['bus_id', 'trip_id', 'line_id']
    },
    'trip_end': {
        'name': 'Trip End',
        'description': 'Notifications when trips complete',
        'required_fields': ['bus_number', 'line_name'],
        'optional_fields': ['bus_id', 'trip_id', 'line_id']
    },
    'service_alert': {
        'name': 'Service Alert',
        'description': 'General service alerts and announcements',
        'required_fields': ['message'],
        'optional_fields': ['severity', 'affected_lines', 'alert_id']
    }
}

# Push Notification Channels for Android
ANDROID_NOTIFICATION_CHANNELS = {
    'default': {
        'name': 'General Notifications',
        'description': 'General app notifications',
        'importance': 3,  # IMPORTANCE_DEFAULT
        'sound': True,
        'vibration': True,
        'lights': True
    },
    'bus_arrivals': {
        'name': 'Bus Arrivals',
        'description': 'Notifications about bus arrivals',
        'importance': 4,  # IMPORTANCE_HIGH
        'sound': True,
        'vibration': True,
        'lights': True
    },
    'bus_delays': {
        'name': 'Bus Delays',
        'description': 'Notifications about bus delays',
        'importance': 4,  # IMPORTANCE_HIGH
        'sound': True,
        'vibration': True,
        'lights': True
    },
    'service_alerts': {
        'name': 'Service Alerts',
        'description': 'Important service alerts',
        'importance': 5,  # IMPORTANCE_MAX
        'sound': True,
        'vibration': True,
        'lights': True,
        'bypass_dnd': True
    },
    'promotions': {
        'name': 'Promotions',
        'description': 'Promotional offers and announcements',
        'importance': 2,  # IMPORTANCE_LOW
        'sound': False,
        'vibration': False,
        'lights': False
    }
}

# Rate Limiting
RATE_LIMIT_CONFIG = {
    'firebase_requests_per_minute': FCM_RATE_LIMIT_PER_MINUTE,
    'user_notifications_per_hour': 50,
    'bulk_notification_max_users': 10000,
    'api_requests_per_minute': 60
}

# Feature Flags
FEATURES = {
    'push_notifications': FIREBASE_CREDENTIALS_PATH is not None,
    'email_notifications': EMAIL_NOTIFICATION_ENABLED,
    'sms_notifications': SMS_NOTIFICATION_ENABLED,
    'notification_analytics': True,
    'health_monitoring': True,
    'batch_processing': True,
    'topic_messaging': False,  # TODO: Implement topic-based messaging
    'rich_notifications': True,  # Images, actions, etc.
    'scheduled_notifications': True,
    'quiet_hours': True,
    'user_preferences': True
}