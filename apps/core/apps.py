"""
Django app configuration for the buses app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    """
    Configuration for the buses app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = _("Core API")