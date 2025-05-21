"""
Django app configuration for the lines app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LinesConfig(AppConfig):
    """
    Configuration for the lines app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lines"
    verbose_name = _("Lines")