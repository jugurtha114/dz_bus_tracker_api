"""
Admin configuration for the tracking app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)


@admin.register(BusLine)
class BusLineAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BusLine model.
    """
    list_display = (
        "bus",
        "line",
        "is_active",
        "tracking_status",
        "start_time",
        "end_time",
    )
    list_filter = ("is_active", "tracking_status", "line", "created_at")
    search_fields = ("bus__license_plate", "line__code", "line__name")
    raw_id_fields = ("bus", "line")
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "line",
                "is_active",
                "tracking_status",
            ),
        }),
        (_("Trip"), {
            "fields": (
                "trip_id",
                "start_time",
                "end_time",
            ),
        }),
    )


@admin.register(LocationUpdate)
class LocationUpdateAdmin(admin.ModelAdmin):
    """
    Admin configuration for the LocationUpdate model.
    """
    list_display = (
        "bus",
        "latitude",
        "longitude",
        "speed",
        "created_at",
        "line",
        "nearest_stop",
    )
    list_filter = ("created_at", "line", "nearest_stop")
    search_fields = ("bus__license_plate", "line__code", "line__name")
    raw_id_fields = ("bus", "line", "nearest_stop")
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "line",
                "trip_id",
            ),
        }),
        (_("Location"), {
            "fields": (
                "latitude",
                "longitude",
                "altitude",
                "heading",
                "accuracy",
            ),
        }),
        (_("Stop"), {
            "fields": (
                "nearest_stop",
                "distance_to_stop",
            ),
        }),
    )


@admin.register(PassengerCount)
class PassengerCountAdmin(admin.ModelAdmin):
    """
    Admin configuration for the PassengerCount model.
    """
    list_display = (
        "bus",
        "count",
        "capacity",
        "occupancy_rate",
        "created_at",
        "line",
        "stop",
    )
    list_filter = ("created_at", "line", "stop")
    search_fields = ("bus__license_plate", "line__code", "line__name")
    raw_id_fields = ("bus", "line", "stop")
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "line",
                "trip_id",
                "stop",
            ),
        }),
        (_("Passengers"), {
            "fields": (
                "count",
                "capacity",
                "occupancy_rate",
            ),
        }),
    )


@admin.register(WaitingPassengers)
class WaitingPassengersAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WaitingPassengers model.
    """
    list_display = (
        "stop",
        "line",
        "count",
        "reported_by",
        "created_at",
    )
    list_filter = ("created_at", "line", "stop")
    search_fields = ("stop__name", "line__code", "line__name")
    raw_id_fields = ("stop", "line", "reported_by")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Trip model.
    """
    list_display = (
        "bus",
        "driver",
        "line",
        "start_time",
        "end_time",
        "is_completed",
        "distance",
        "max_passengers",
    )
    list_filter = ("is_completed", "start_time", "line")
    search_fields = (
        "bus__license_plate",
        "driver__user__email",
        "driver__user__first_name",
        "driver__user__last_name",
        "line__code",
        "line__name",
    )
    raw_id_fields = ("bus", "driver", "line", "start_stop", "end_stop")
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "driver",
                "line",
                "is_completed",
            ),
        }),
        (_("Time and Location"), {
            "fields": (
                "start_time",
                "end_time",
                "start_stop",
                "end_stop",
            ),
        }),
        (_("Statistics"), {
            "fields": (
                "distance",
                "average_speed",
                "max_passengers",
                "total_stops",
                "notes",
            ),
        }),
    )


@admin.register(Anomaly)
class AnomalyAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Anomaly model.
    """
    list_display = (
        "bus",
        "type",
        "severity",
        "created_at",
        "resolved",
        "resolved_at",
    )
    list_filter = ("type", "severity", "resolved", "created_at")
    search_fields = ("bus__license_plate", "description", "resolution_notes")
    raw_id_fields = ("bus", "trip")
    fieldsets = (
        (None, {
            "fields": (
                "bus",
                "trip",
                "type",
                "severity",
                "description",
            ),
        }),
        (_("Location"), {
            "fields": (
                "location_latitude",
                "location_longitude",
            ),
        }),
        (_("Resolution"), {
            "fields": (
                "resolved",
                "resolved_at",
                "resolution_notes",
            ),
        }),
    )