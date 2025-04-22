from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AnalyticsConfig(AppConfig):
    name = "apps.analytics"
    verbose_name = _("Analytics")
    
    def ready(self):
        try:
            import apps.analytics.signals  # noqa F401
        except ImportError:
            pass
