"""
Admin configuration for the notifications app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import DeviceToken, Notification


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    """
    Admin configuration for the DeviceToken model.
    """
    list_display = (
        "user",
        "device_type",
        "is_active",
        "created_at",
        "last_used",
    )
    list_filter = ("device_type", "is_active", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "token",
    )
    raw_id_fields = ("user",)
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "token",
                "device_type",
                "is_active",
            ),
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Notification model.
    """
    list_display = (
        "user",
        "notification_type",
        "title",
        "channel",
        "is_read",
        "created_at",
    )
    list_filter = (
        "notification_type",
        "channel",
        "is_read",
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "title",
        "message",
    )
    raw_id_fields = ("user",)
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "notification_type",
                "channel",
            ),
        }),
        (_("Content"), {
            "fields": (
                "title",
                "message",
                "data",
            ),
        }),
        (_("Status"), {
            "fields": (
                "is_read",
                "read_at",
            ),
        }),
    )