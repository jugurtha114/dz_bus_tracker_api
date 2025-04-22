from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TrackingConfig(AppConfig):
    name = "apps.tracking"
    verbose_name = _("Tracking")
    
    def ready(self):
        try:
            import apps.tracking.signals  # noqa F401
        except ImportError:
            pass
