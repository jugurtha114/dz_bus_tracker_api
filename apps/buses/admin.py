"""
Admin configuration for the buses app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Bus, BusLocation


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Bus model.
    """
    list_display = (
        "license_plate",
        "driver",
        "model",
        "manufacturer",
        "capacity",
        "status",
        "is_active",
        "is_approved",
    )
    list_filter = ("status", "is_active", "is_approved", "is_air_conditioned")
    search_fields = ("license_plate", "model", "manufacturer", "driver__user__email")
    raw_id_fields = ("driver",)
    fieldsets = (
        (None, {
            "fields": (
                "license_plate",
                "driver",
                "status",
                "is_active",
                "is_approved",
            ),
        }),
        (_("Bus details"), {
            "fields": (
                "model",
                "manufacturer",
                "year",
                "capacity",
                "is_air_conditioned",
                "photo",
                "features",
                "description",
            ),
        }),
    )


@admin.register(BusLocation)
class BusLocationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BusLocation model.
    """
    list_display = (
        "bus",
        "latitude",
        "longitude",
        "speed",
        "heading",
        "is_tracking_active",
        "passenger_count",
        "created_at",
    )
    list_filter = ("is_tracking_active", "created_at")
    search_fields = ("bus__license_plate",)
    raw_id_fields = ("bus",)
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "is_tracking_active",
                "passenger_count",
            ),
        }),
        (_("Location"), {
            "fields": (
                "latitude",
                "longitude",
                "altitude",
                "accuracy",
            ),
        }),
        (_("Movement"), {
            "fields": (
                "speed",
                "heading",
            ),
        }),
    )