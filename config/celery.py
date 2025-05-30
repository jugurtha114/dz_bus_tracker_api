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
