# apps/schedules/admin.py
from django.contrib import admin
from .models import Schedule, ScheduleException

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['id', 'line', 'bus', 'driver', 'start_time', 'end_time', 'days_of_week', 'is_active']
    list_filter = ['is_active', 'line']

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'schedule', 'date', 'reason']
    list_filter = ['date']

