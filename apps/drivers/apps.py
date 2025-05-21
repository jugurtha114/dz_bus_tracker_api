"""
Django app configuration for the drivers app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DriversConfig(AppConfig):
    """
    Configuration for the drivers app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drivers"
    verbose_name = _("Drivers")