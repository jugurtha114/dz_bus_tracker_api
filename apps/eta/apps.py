from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ETAConfig(AppConfig):
    name = "apps.eta"
    verbose_name = _("ETA")
    
    def ready(self):
        try:
            import apps.eta.signals  # noqa F401
        except ImportError:
            pass
