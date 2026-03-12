"""
Celery configuration for DZ Bus Tracker.
"""
import os

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("dz_bus_tracker")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Debug task that prints request information."""
    print(f"Request: {self.request!r}")


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Set up periodic tasks that run on a schedule."""
    # Clean old location data every day at midnight
    sender.add_periodic_task(
        crontab(hour=0, minute=0),
        sender.signature("apps.tracking.tasks.clean_old_location_data"),
        name="clean-old-location-data-daily",
    )

    # Process scheduled notifications every minute
    sender.add_periodic_task(
        60.0,
        sender.signature("notifications.process_scheduled"),
        name="process-scheduled-notifications",
    )

    # Check for arrival notifications every 2 minutes
    sender.add_periodic_task(
        120.0,
        sender.signature("notifications.check_arrival_notifications"),
        name="check-arrival-notifications",
    )

    # Send trip updates every minute
    sender.add_periodic_task(
        60.0,
        sender.signature("notifications.send_trip_updates"),
        name="send-trip-updates",
    )

    # Clean up old notifications daily at 3 AM
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        sender.signature("notifications.cleanup_old_notifications"),
        name="cleanup-old-notifications-daily",
    )

    # Auto-sync offline caches every 30 minutes
    sender.add_periodic_task(
        1800.0,
        sender.signature("offline_mode.check_auto_sync"),
        name="check-auto-sync",
    )

    # Clean expired cache daily at 4 AM
    sender.add_periodic_task(
        crontab(hour=4, minute=0),
        sender.signature("offline_mode.clean_expired_cache"),
        name="clean-expired-cache-daily",
    )

    # Process sync queues every 10 minutes
    sender.add_periodic_task(
        600.0,
        sender.signature("offline_mode.process_sync_queues"),
        name="process-sync-queues",
    )

    # Update cache statistics every hour at :30
    sender.add_periodic_task(
        crontab(minute=30),
        sender.signature("offline_mode.update_cache_statistics"),
        name="update-cache-statistics-hourly",
    )

    # Clean up old logs weekly on Sunday at 5 AM
    sender.add_periodic_task(
        crontab(day_of_week=0, hour=5, minute=0),
        sender.signature("offline_mode.cleanup_old_logs"),
        name="cleanup-old-logs-weekly",
    )

    # Notify waiting passengers when bus is approaching (every 30 seconds)
    sender.add_periodic_task(
        30.0,
        sender.signature("apps.tracking.tasks.notify_waiting_passengers_on_arrival"),
        name="notify-waiting-passengers-arrival",
    )
