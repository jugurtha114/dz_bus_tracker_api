"""
Admin configuration for the lines app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Line, LineStop, Schedule, Stop


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Stop model.
    """
    list_display = (
        "name",
        "latitude",
        "longitude",
        "address",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "address")
    fieldsets = (
        (None, {
            "fields": (
                "name",
                "is_active",
            ),
        }),
        (_("Location"), {
            "fields": (
                "latitude",
                "longitude",
                "address",
            ),
        }),
        (_("Details"), {
            "fields": (
                "description",
                "features",
                "photo",
            ),
        }),
    )


class LineStopInline(admin.TabularInline):
    """
    Inline admin for LineStop model.
    """
    model = LineStop
    extra = 1
    ordering = ("order",)


class ScheduleInline(admin.TabularInline):
    """
    Inline admin for Schedule model.
    """
    model = Schedule
    extra = 1
    ordering = ("day_of_week", "start_time")


@admin.register(Line)
class LineAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Line model.
    """
    list_display = (
        "code",
        "name",
        "color",
        "frequency",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    inlines = [LineStopInline, ScheduleInline]
    fieldsets = (
        (None, {
            "fields": (
                "code",
                "name",
                "is_active",
            ),
        }),
        (_("Details"), {
            "fields": (
                "description",
                "color",
                "frequency",
            ),
        }),
    )


@admin.register(LineStop)
class LineStopAdmin(admin.ModelAdmin):
    """
    Admin configuration for the LineStop model.
    """
    list_display = (
        "line",
        "stop",
        "order",
        "distance_from_previous",
        "average_time_from_previous",
    )
    list_filter = ("line",)
    search_fields = ("line__code", "line__name", "stop__name")
    ordering = ("line", "order")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Schedule model.
    """
    list_display = (
        "line",
        "day_of_week",
        "start_time",
        "end_time",
        "frequency_minutes",
        "is_active",
    )
    list_filter = ("day_of_week", "is_active", "line")
    search_fields = ("line__code", "line__name")
    ordering = ("line", "day_of_week", "start_time")