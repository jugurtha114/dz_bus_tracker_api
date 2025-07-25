"""
Celery configuration for DZ Bus Tracker.
"""
import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

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
        "tasks.tracking.clean_old_location_data.s",
    )

    # Clean inactive buses every hour
    sender.add_periodic_task(
        crontab(minute=0),
        "tasks.buses.clean_inactive_buses.s",
    )

    # Update driver stats every day at 1 AM
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        "tasks.drivers.update_driver_stats.s",
    )

    # Generate daily reports at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        "tasks.periodic.generate_daily_reports.s",
    )
    
    # Process scheduled notifications every minute
    sender.add_periodic_task(
        60.0,  # Every 60 seconds
        "notifications.process_scheduled",
    )
    
    # Check for arrival notifications every 2 minutes
    sender.add_periodic_task(
        120.0,  # Every 120 seconds
        "notifications.check_arrival_notifications",
    )
    
    # Send trip updates every minute
    sender.add_periodic_task(
        60.0,  # Every 60 seconds
        "notifications.send_trip_updates",
    )
    
    # Clean up old notifications daily at 3 AM
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        "notifications.cleanup_old_notifications",
    )
    
    # Update leaderboards every hour
    sender.add_periodic_task(
        crontab(minute=0),  # Every hour at minute 0
        "gamification.update_leaderboards",
    )
    
    # Check challenge completion daily at 1 AM
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        "gamification.check_challenge_completion",
    )
    
    # Award daily bonus at 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        "gamification.award_daily_bonus",
    )
