"""
Django app configuration for the accounts app.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    """
    Configuration for the accounts app.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = _("Accounts")

    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        import apps.accounts.signals  # noqa
        