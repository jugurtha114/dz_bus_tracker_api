
import os
from celery import Celery

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

# Create the app
app = Celery('dz_bus_tracker')

# Use the configuration from the Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')