from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LinesConfig(AppConfig):
    name = "apps.lines"
    verbose_name = _("Lines")
    
    def ready(self):
        try:
            import apps.lines.signals  # noqa F401
        except ImportError:
            pass
