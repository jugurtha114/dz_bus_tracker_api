"""
Admin configuration for the tracking app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Anomaly,
    BusLine,
    BusWaitingList,
    CurrencyTransaction,
    DriverPerformanceScore,
    LocationUpdate,
    PassengerCount,
    PremiumFeature,
    ReputationScore,
    Trip,
    UserPremiumFeature,
    VirtualCurrency,
    WaitingCountReport,
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


@admin.register(BusWaitingList)
class BusWaitingListAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BusWaitingList model.
    """
    list_display = (
        "user",
        "bus",
        "stop",
        "joined_at",
        "is_active",
        "estimated_arrival",
        "waiting_duration_display",
    )
    list_filter = ("is_active", "joined_at", "bus__driver")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "bus__license_plate",
        "stop__name",
    )
    raw_id_fields = ("user", "bus", "stop")
    readonly_fields = ("joined_at", "waiting_duration_display")
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "bus",
                "stop",
                "is_active",
            ),
        }),
        (_("Timing"), {
            "fields": (
                "joined_at",
                "estimated_arrival",
                "left_at",
                "notified_on_arrival",
            ),
        }),
    )

    def waiting_duration_display(self, obj):
        """Display waiting duration in minutes."""
        if obj.is_active:
            from django.utils import timezone
            duration = timezone.now() - obj.joined_at
            return f"{int(duration.total_seconds() / 60)} minutes"
        elif obj.left_at:
            duration = obj.left_at - obj.joined_at
            return f"{int(duration.total_seconds() / 60)} minutes"
        return "-"
    waiting_duration_display.short_description = _("Waiting Duration")


@admin.register(WaitingCountReport)
class WaitingCountReportAdmin(admin.ModelAdmin):
    """
    Admin configuration for the WaitingCountReport model.
    """
    list_display = (
        "reporter",
        "stop",
        "bus",
        "reported_count",
        "confidence_score",
        "verification_status",
        "location_verified",
        "created_at",
    )
    list_filter = (
        "verification_status",
        "confidence_level",
        "location_verified",
        "is_verified",
        "created_at",
    )
    search_fields = (
        "reporter__email",
        "reporter__first_name",
        "reporter__last_name",
        "stop__name",
        "bus__license_plate",
    )
    raw_id_fields = ("reporter", "stop", "bus", "line", "verified_by")
    readonly_fields = ("confidence_score", "distance_from_stop_display")
    fieldsets = (
        (None, {
            "fields": (
                "reporter",
                "stop",
                "bus",
                "line",
                "reported_count",
                "confidence_level",
                "confidence_score",
            ),
        }),
        (_("Location"), {
            "fields": (
                "reporter_latitude",
                "reporter_longitude",
                "location_verified",
                "distance_from_stop_display",
            ),
        }),
        (_("Verification"), {
            "fields": (
                "is_verified",
                "verification_status",
                "verified_by",
                "actual_count",
                "verified_at",
            ),
        }),
    )

    def distance_from_stop_display(self, obj):
        """Display distance from reporter to stop."""
        if obj.reporter_latitude and obj.reporter_longitude and obj.stop:
            from apps.core.utils.geo import calculate_distance
            distance = calculate_distance(
                float(obj.reporter_latitude),
                float(obj.reporter_longitude),
                float(obj.stop.latitude),
                float(obj.stop.longitude)
            )
            return f"{distance * 1000:.0f} meters" if distance else "-"
        return "-"
    distance_from_stop_display.short_description = _("Distance from Stop")


@admin.register(ReputationScore)
class ReputationScoreAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ReputationScore model.
    """
    list_display = (
        "user",
        "reputation_level",
        "total_reports",
        "correct_reports",
        "accuracy_rate_display",
        "trust_multiplier",
        "last_updated",
    )
    list_filter = ("reputation_level", "last_updated")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    raw_id_fields = ("user",)
    readonly_fields = ("accuracy_rate_display", "last_updated")
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "reputation_level",
                "trust_multiplier",
            ),
        }),
        (_("Statistics"), {
            "fields": (
                "total_reports",
                "correct_reports",
                "accuracy_rate_display",
                "last_updated",
            ),
        }),
    )

    def accuracy_rate_display(self, obj):
        """Display accuracy rate as percentage."""
        return f"{obj.accuracy_rate:.1f}%"
    accuracy_rate_display.short_description = _("Accuracy Rate")


@admin.register(VirtualCurrency)
class VirtualCurrencyAdmin(admin.ModelAdmin):
    """
    Admin configuration for the VirtualCurrency model.
    """
    list_display = (
        "user",
        "balance",
        "lifetime_earned",
        "lifetime_spent",
        "last_transaction",
    )
    list_filter = ("last_transaction", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    raw_id_fields = ("user",)
    readonly_fields = ("last_transaction",)
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "balance",
            ),
        }),
        (_("Statistics"), {
            "fields": (
                "lifetime_earned",
                "lifetime_spent",
                "last_transaction",
            ),
        }),
    )


@admin.register(CurrencyTransaction)
class CurrencyTransactionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the CurrencyTransaction model.
    """
    list_display = (
        "user",
        "amount_display",
        "transaction_type",
        "description",
        "balance_after",
        "created_at",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "description",
    )
    raw_id_fields = ("user", "related_report")
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "amount",
                "transaction_type",
                "description",
                "balance_after",
            ),
        }),
        (_("Related Data"), {
            "fields": (
                "related_report",
                "metadata",
            ),
        }),
    )

    def amount_display(self, obj):
        """Display amount with + or - sign."""
        sign = "+" if obj.amount >= 0 else ""
        return f"{sign}{obj.amount}"
    amount_display.short_description = _("Amount")


@admin.register(DriverPerformanceScore)
class DriverPerformanceScoreAdmin(admin.ModelAdmin):
    """
    Admin configuration for the DriverPerformanceScore model.
    """
    list_display = (
        "driver_name",
        "performance_level",
        "total_trips",
        "on_time_percentage_display",
        "safety_score",
        "passenger_rating",
        "current_streak",
        "last_updated",
    )
    list_filter = ("performance_level", "last_updated")
    search_fields = (
        "driver__user__email",
        "driver__user__first_name",
        "driver__user__last_name",
    )
    raw_id_fields = ("driver",)
    readonly_fields = ("on_time_percentage_display", "last_updated")
    fieldsets = (
        (None, {
            "fields": (
                "driver",
                "performance_level",
            ),
        }),
        (_("Trip Statistics"), {
            "fields": (
                "total_trips",
                "on_time_trips",
                "on_time_percentage_display",
            ),
        }),
        (_("Performance Metrics"), {
            "fields": (
                "safety_score",
                "passenger_rating",
                "fuel_efficiency_score",
                "report_verification_accuracy",
            ),
        }),
        (_("Streaks"), {
            "fields": (
                "current_streak",
                "best_streak",
            ),
        }),
    )

    def driver_name(self, obj):
        """Display driver's name."""
        return obj.driver.user.get_full_name() or obj.driver.user.email
    driver_name.short_description = _("Driver")

    def on_time_percentage_display(self, obj):
        """Display on-time percentage."""
        return f"{obj.on_time_percentage:.1f}%"
    on_time_percentage_display.short_description = _("On-Time %")


@admin.register(PremiumFeature)
class PremiumFeatureAdmin(admin.ModelAdmin):
    """
    Admin configuration for the PremiumFeature model.
    """
    list_display = (
        "name",
        "feature_type",
        "target_users",
        "cost_coins",
        "duration_days",
        "required_level",
        "is_active",
    )
    list_filter = ("feature_type", "target_users", "is_active", "required_level")
    search_fields = ("name", "description")
    fieldsets = (
        (None, {
            "fields": (
                "name",
                "feature_type",
                "description",
                "is_active",
            ),
        }),
        (_("Pricing & Duration"), {
            "fields": (
                "cost_coins",
                "duration_days",
            ),
        }),
        (_("Access Control"), {
            "fields": (
                "target_users",
                "required_level",
            ),
        }),
    )


@admin.register(UserPremiumFeature)
class UserPremiumFeatureAdmin(admin.ModelAdmin):
    """
    Admin configuration for the UserPremiumFeature model.
    """
    list_display = (
        "user_name",
        "feature_name",
        "purchased_at",
        "expires_at",
        "is_active",
        "is_expired_display",
        "coins_spent",
    )
    list_filter = ("is_active", "purchased_at", "feature__feature_type")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "feature__name",
    )
    raw_id_fields = ("user", "feature")
    readonly_fields = ("purchased_at", "is_expired_display")
    fieldsets = (
        (None, {
            "fields": (
                "user",
                "feature",
                "is_active",
            ),
        }),
        (_("Timing"), {
            "fields": (
                "purchased_at",
                "expires_at",
                "is_expired_display",
            ),
        }),
        (_("Payment"), {
            "fields": (
                "coins_spent",
            ),
        }),
    )

    def user_name(self, obj):
        """Display user's name."""
        return obj.user.get_full_name() or obj.user.email
    user_name.short_description = _("User")

    def feature_name(self, obj):
        """Display feature name."""
        return obj.feature.name
    feature_name.short_description = _("Feature")

    def is_expired_display(self, obj):
        """Display if feature is expired."""
        return "Yes" if obj.is_expired else "No"
    is_expired_display.short_description = _("Expired")