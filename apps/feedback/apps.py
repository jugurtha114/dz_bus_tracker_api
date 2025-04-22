from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FeedbackConfig(AppConfig):
    name = "apps.feedback"
    verbose_name = _("Feedback")
    
    def ready(self):
        try:
            pass
        except ImportError:
            pass
