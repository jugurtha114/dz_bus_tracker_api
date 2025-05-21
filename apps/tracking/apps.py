"""
Django app configuration for the tracking app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TrackingConfig(AppConfig):
    """
    Configuration for the tracking app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tracking"
    verbose_name = _("Tracking")