from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PassengersConfig(AppConfig):
    name = "apps.passengers"
    verbose_name = _("Passengers")
    
    def ready(self):
        try:
            import apps.passengers.signals  # noqa F401
        except ImportError:
            pass
