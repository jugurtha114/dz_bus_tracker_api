from django.contrib import admin
from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'journey_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(SavedLocation)
class SavedLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger', 'name', 'address', 'is_favorite', 'is_active')
    list_filter = ('is_favorite', 'is_active')
    search_fields = ('name', 'address', 'passenger__user__email')
    raw_id_fields = ('passenger',)


@admin.register(TripHistory)
class TripHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger', 'line', 'start_stop', 'end_stop', 'status', 'start_time')
    list_filter = ('status', 'start_time')
    search_fields = ('passenger__user__email', 'line__name')
    raw_id_fields = ('passenger', 'line', 'start_stop', 'end_stop')
    date_hierarchy = 'start_time'


@admin.register(FeedbackRequest)
class FeedbackRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger', 'line', 'is_completed', 'sent_at', 'expires_at')
    list_filter = ('is_completed', 'sent_at')
    search_fields = ('passenger__user__email', 'line__name')
    raw_id_fields = ('passenger', 'trip', 'line')
    date_hierarchy = 'sent_at'
