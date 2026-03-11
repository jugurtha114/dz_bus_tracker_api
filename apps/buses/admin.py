"""
Admin configuration for the buses app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Bus


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
