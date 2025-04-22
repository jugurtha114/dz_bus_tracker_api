from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BusesConfig(AppConfig):
    name = "apps.buses"
    verbose_name = _("Buses")
    
    def ready(self):
        try:
            import apps.buses.signals  # noqa F401
        except ImportError:
            pass
