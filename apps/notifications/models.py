"""
Models for the notifications app.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.constants import (
    NOTIFICATION_CHANNEL_CHOICES,
    NOTIFICATION_CHANNEL_IN_APP,
    NOTIFICATION_TYPE_CHOICES,
)
from apps.core.models import BaseModel


class DeviceToken(BaseModel):
    """
    Model for device tokens for push notifications.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_tokens",
        verbose_name=_("user"),
    )
    token = models.TextField(_("token"))
    device_type = models.CharField(
        _("device type"),
        max_length=20,
        choices=[
            ("ios", "iOS"),
            ("android", "Android"),
            ("web", "Web"),
        ],
    )
    is_active = models.BooleanField(_("active"), default=True)
    last_used = models.DateTimeField(
        _("last used"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("device token")
        verbose_name_plural = _("device tokens")
        ordering = ["-created_at"]
        unique_together = [["user", "token"]]

    def __str__(self):
        return f"{self.user} - {self.device_type} token"


class Notification(BaseModel):
    """
    Model for notifications.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("user"),
    )
    notification_type = models.CharField(
        _("notification type"),
        max_length=50,
        choices=NOTIFICATION_TYPE_CHOICES,
    )
    title = models.CharField(_("title"), max_length=255)
    message = models.TextField(_("message"))
    channel = models.CharField(
        _("channel"),
        max_length=20,
        choices=NOTIFICATION_CHANNEL_CHOICES,
        default=NOTIFICATION_CHANNEL_IN_APP,
    )
    is_read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    data = models.JSONField(
        _("data"),
        default=dict,
        blank=True,
        help_text=_("Additional data for the notification"),
    )

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.title} ({self.created_at})"