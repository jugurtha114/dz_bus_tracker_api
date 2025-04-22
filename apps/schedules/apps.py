from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SchedulesConfig(AppConfig):
    name = "apps.schedules"
    verbose_name = _("Schedules")
    
    def ready(self):
        try:
            import apps.schedules.signals  # noqa F401
        except ImportError:
            pass
