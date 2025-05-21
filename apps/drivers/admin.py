"""
Admin configuration for the drivers app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Driver, DriverRating


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Driver model.
    """
    list_display = (
        "user",
        "phone_number",
        "id_card_number",
        "status",
        "rating",
        "total_ratings",
        "is_active",
        "is_available",
    )
    list_filter = ("status", "is_active", "is_available")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "phone_number",
        "id_card_number",
    )
    raw_id_fields = ("user",)
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "phone_number",
                "status",
                "rejection_reason",
                "is_active",
                "is_available",
            ),
        }),
        (_("Identification"), {
            "fields": (
                "id_card_number",
                "id_card_photo",
                "driver_license_number",
                "driver_license_photo",
            ),
        }),
        (_("Experience"), {
            "fields": (
                "years_of_experience",
            ),
        }),
        (_("Ratings"), {
            "fields": (
                "rating",
                "total_ratings",
            ),
        }),
    )
    readonly_fields = ("rating", "total_ratings")


@admin.register(DriverRating)
class DriverRatingAdmin(admin.ModelAdmin):
    """
    Admin configuration for the DriverRating model.
    """
    list_display = (
        "driver",
        "user",
        "rating",
        "created_at",
    )
    list_filter = ("rating", "created_at")
    search_fields = (
        "driver__user__email",
        "driver__user__first_name",
        "driver__user__last_name",
        "user__email",
        "user__first_name",
        "user__last_name",
        "comment",
    )
    raw_id_fields = ("driver", "user")