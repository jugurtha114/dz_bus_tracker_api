from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DriversConfig(AppConfig):
    name = "apps.drivers"
    verbose_name = _("Drivers")
    
    def ready(self):
        try:
            import apps.drivers.signals  # noqa F401
        except ImportError:
            pass
