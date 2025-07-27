# Professional Push Notification System

A comprehensive, production-ready push notification system for the DZ Bus Tracker application, built with Firebase Cloud Messaging (FCM) and best practices.

## 🚀 Features

### Core Functionality
- **Firebase Cloud Messaging (FCM)** integration with retry logic and error handling
- **Multi-channel notifications**: Push, Email, SMS, In-app
- **Rich notification templates** with internationalization support
- **Device token management** with automatic validation and cleanup
- **Batch notifications** for efficient mass messaging
- **Scheduled notifications** with intelligent timing
- **User preferences** with quiet hours and channel selection

### Professional Features
- **Rate limiting** and quota management
- **Comprehensive monitoring** and health checks
- **Analytics and reporting** with user insights
- **Automatic error recovery** and token cleanup
- **Background task processing** with Celery
- **Template-based messaging** for consistency
- **Security-first design** with token validation

### Advanced Capabilities
- **Topic-based messaging** for broadcast notifications
- **Delivery tracking** and success metrics
- **A/B testing support** through templates
- **Geofencing integration** for location-based notifications
- **Rich media support** (images, actions, sounds)
- **Multi-language support** with Django i18n

## 📁 Project Structure

```
apps/notifications/
├── __init__.py
├── README.md                    # This file
├── config.py                   # Configuration settings
├── models.py                   # Database models
├── firebase.py                 # Core FCM service
├── enhanced_services.py        # High-level notification services
├── enhanced_tasks.py           # Celery background tasks
├── enhanced_views.py           # API endpoints
├── templates.py                # Notification templates
├── monitoring.py               # Health monitoring and analytics
├── tests/                      # Comprehensive test suite
│   ├── test_firebase.py
│   └── test_enhanced_services.py
└── migrations/                 # Database migrations
```

## 🛠️ Setup Instructions

### 1. Firebase Configuration

1. **Download Service Account Key**:
   ```bash
   # Run the setup script
   python scripts/setup_firebase.py
   ```

2. **Follow the instructions** to download your Firebase service account key from:
   - Firebase Console → Project Settings → Service Accounts
   - Generate new private key → Save as `firebase-service-account.json`

3. **Configure Environment**:
   ```bash
   # Add to your .env file
   FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json
   FIREBASE_PROJECT_ID=your-project-id
   ```

### 2. Django Settings

Add to your Django settings:

```python
# Firebase Configuration
FIREBASE_CREDENTIALS_PATH = env("FIREBASE_CREDENTIALS_PATH", default=None)
FIREBASE_PROJECT_ID = env("FIREBASE_PROJECT_ID", default=None)

# Celery Configuration for Notifications
CELERY_BEAT_SCHEDULE.update({
    'process-scheduled-notifications': {
        'task': 'notifications.process_scheduled_notifications',
        'schedule': 60.0,  # Every minute
    },
    'cleanup-invalid-tokens': {
        'task': 'notifications.cleanup_invalid_tokens',
        'schedule': 3600.0,  # Every hour
    },
    'notification-health-check': {
        'task': 'notifications.health_check',
        'schedule': 300.0,  # Every 5 minutes
    },
})
```

### 3. Database Migration

```bash
python manage.py migrate
```

### 4. Test the Setup

```bash
# Test Firebase initialization
python test_firebase.py

# Run comprehensive tests
python manage.py test apps.notifications
```

## 📱 Client Integration

### Android Setup

1. **Add Firebase SDK** to your Android app:
   ```gradle
   implementation 'com.google.firebase:firebase-messaging:23.0.0'
   ```

2. **Configure Notification Channels**:
   ```kotlin
   private fun createNotificationChannels() {
       val channels = listOf(
           NotificationChannel("bus_arrivals", "Bus Arrivals", NotificationManager.IMPORTANCE_HIGH),
           NotificationChannel("bus_delays", "Bus Delays", NotificationManager.IMPORTANCE_HIGH),
           NotificationChannel("service_alerts", "Service Alerts", NotificationManager.IMPORTANCE_MAX)
       )
       
       val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
       channels.forEach { manager.createNotificationChannel(it) }
   }
   ```

3. **Register Device Token**:
   ```kotlin
   FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
       if (!task.isSuccessful) return@addOnCompleteListener
       
       val token = task.result
       // Send token to your backend
       registerTokenWithBackend(token)
   }
   ```

### iOS Setup

1. **Add Firebase SDK** to your iOS app:
   ```swift
   import FirebaseMessaging
   ```

2. **Request Notification Permissions**:
   ```swift
   UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
       if granted {
           DispatchQueue.main.async {
               UIApplication.shared.registerForRemoteNotifications()
           }
       }
   }
   ```

3. **Handle Token Registration**:
   ```swift
   Messaging.messaging().token { token, error in
       if let error = error {
           print("Error fetching FCM registration token: \\(error)")
       } else if let token = token {
           // Send token to your backend
           registerTokenWithBackend(token)
       }
   }
   ```

## 🔧 API Usage

### Register Device Token

```bash
POST /api/v1/notifications/device-tokens/register/
{
    "token": "fcm_device_token_here",
    "device_type": "android",
    "device_info": {
        "model": "Galaxy S21",
        "manufacturer": "Samsung"
    },
    "app_version": "1.2.0",
    "os_version": "11"
}
```

### Send Notification

```bash
POST /api/v1/notifications/notifications/send_notification/
{
    "user_ids": ["user_uuid_1", "user_uuid_2"],
    "template_type": "bus_arrival",
    "channels": ["push", "in_app"],
    "priority": "high",
    "template_data": {
        "bus_number": "101",
        "stop_name": "Main Station",
        "minutes": 5,
        "line_name": "Blue Line"
    }
}
```

### Bulk Notifications

```bash
POST /api/v1/notifications/notifications/send_bulk/
{
    "user_ids": ["user1", "user2", "user3"],
    "template_type": "service_alert",
    "channels": ["push"],
    "template_data": {
        "title": "Service Update",
        "message": "Bus service will be delayed due to traffic",
        "severity": "warning"
    }
}
```

### Update Preferences

```bash
PATCH /api/v1/notifications/preferences/my_preferences/
{
    "bus_arrival": {
        "enabled": true,
        "channels": ["push", "in_app"],
        "minutes_before_arrival": 10,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00"
    }
}
```

## 📊 Monitoring & Analytics

### System Health Check

```bash
GET /api/v1/notifications/notifications/system_health/
```

Response:
```json
{
    "status": "healthy",
    "score": 95.5,
    "summary": "All notification systems are operating normally",
    "metrics": [
        {
            "name": "firebase_connectivity",
            "value": true,
            "status": "healthy",
            "message": "Firebase is connected and ready"
        }
    ]
}
```

### Notification Statistics

```bash
GET /api/v1/notifications/notifications/stats/?hours=24
```

### User Analytics

```bash
GET /api/v1/notifications/notifications/my_analytics/?days=30
```

## 🎨 Notification Templates

### Available Templates

1. **Bus Arrival** (`bus_arrival`)
   - For notifying users about approaching buses
   - Required: `bus_number`, `stop_name`, `minutes`

2. **Bus Delay** (`bus_delay`)
   - For notifying about bus delays
   - Required: `bus_number`, `line_name`, `delay_minutes`

3. **Service Alert** (`service_alert`)
   - For general service announcements
   - Required: `message`, `severity`

4. **Trip Updates** (`trip_start`, `trip_end`)
   - For trip lifecycle notifications
   - Required: `bus_number`, `line_name`

### Custom Templates

```python
from apps.notifications.templates import NotificationTemplate

class CustomTemplate(NotificationTemplate):
    def get_title(self, **kwargs):
        return f"Custom: {kwargs.get('title', 'Notification')}"
    
    def get_body(self, **kwargs):
        return kwargs.get('message', 'Custom notification body')
    
    def get_icon(self):
        return "ic_custom"
    
    def get_color(self):
        return "#FF5722"

# Register the template
NotificationTemplateFactory.register_template('custom', CustomTemplate)
```

## 🔍 Advanced Features

### Scheduled Notifications

```python
from apps.notifications.services import NotificationService

# Schedule notification for future delivery
NotificationService.schedule_arrival_notification(
    user_id="user_uuid",
    bus_id="bus_uuid",
    stop_id="stop_uuid",
    estimated_arrival=datetime.now() + timedelta(minutes=15)
)
```

### Topic Messaging

```python
from apps.notifications.firebase import FCMService

# Subscribe users to topics
FCMService.subscribe_to_topic(
    tokens=["token1", "token2"],
    topic="line_blue_alerts"
)

# Send to topic
FCMService.send_topic_notification(
    topic="service_alerts",
    notification=notification_data
)
```

### Batch Processing

```python
from apps.notifications.enhanced_tasks import send_bulk_notification_task

# Queue bulk notification
task = send_bulk_notification_task.delay(
    user_ids=user_list,
    template_type="service_alert",
    channels=["push"],
    message="Important service update"
)
```

## 🛡️ Security Features

- **Token Validation**: Automatic validation of FCM tokens
- **Rate Limiting**: Protection against abuse
- **Permission System**: Role-based access control
- **Audit Logging**: Comprehensive activity tracking
- **Data Encryption**: Secure handling of sensitive data
- **Input Validation**: Sanitization of all inputs

## 📈 Performance Optimizations

- **Connection Pooling**: Efficient Firebase connections
- **Batch Processing**: Reduced API calls
- **Caching**: Redis-based caching for frequently accessed data
- **Background Tasks**: Non-blocking notification processing
- **Database Indexing**: Optimized queries
- **Token Cleanup**: Automatic removal of invalid tokens

## 🔧 Maintenance

### Regular Tasks

```bash
# Cleanup old notifications (daily)
python manage.py clean_old_notifications --days=30

# Health check
python manage.py notification_health_check

# Token cleanup
python manage.py cleanup_invalid_tokens
```

### Monitoring Commands

```bash
# Check system status
curl -H "Authorization: Bearer YOUR_TOKEN" \\
     http://localhost:8000/api/v1/notifications/notifications/system_health/

# View statistics
curl -H "Authorization: Bearer YOUR_TOKEN" \\
     http://localhost:8000/api/v1/notifications/notifications/stats/
```

## 🐛 Troubleshooting

### Common Issues

1. **Firebase Not Initialized**
   - Check `FIREBASE_CREDENTIALS_PATH` is set correctly
   - Verify service account key file exists and is valid
   - Run `python scripts/setup_firebase.py` for guidance

2. **Notifications Not Sending**
   - Check device tokens are registered and valid
   - Verify FCM quota limits
   - Check Celery workers are running

3. **High Token Failure Rate**
   - Run token cleanup: `python manage.py cleanup_invalid_tokens`
   - Check app installation/uninstallation patterns
   - Verify token registration process

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger('apps.notifications').setLevel(logging.DEBUG)
```

## 📚 References

- [Firebase Cloud Messaging Documentation](https://firebase.google.com/docs/cloud-messaging)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [DZ Bus Tracker API Documentation](../api/README.md)

## 🤝 Contributing

1. Follow the existing code style and patterns
2. Add comprehensive tests for new features
3. Update documentation for any API changes
4. Ensure all tests pass before submitting PRs

## 📄 License

This notification system is part of the DZ Bus Tracker project and follows the same license terms.