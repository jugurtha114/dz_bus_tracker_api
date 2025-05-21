"""
Django app configuration for the API app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApiConfig(AppConfig):
    """
    Configuration for the API app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    verbose_name = _("API")