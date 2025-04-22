from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from apps.lines.serializers import LineSerializer
from apps.buses.serializers import BusSerializer
from apps.drivers.serializers import DriverSerializer
from .models import Schedule, ScheduleException, ScheduledTrip, MaintenanceSchedule


class ScheduleSerializer(BaseModelSerializer):
    line_details = LineSerializer(source='line', read_only=True)
    bus_details = BusSerializer(source='bus', read_only=True)
    driver_details = DriverSerializer(source='driver', read_only=True)
    days_of_week_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Schedule
        fields = [
            'id', 'line', 'bus', 'driver', 'start_time', 'end_time',
            'days_of_week', 'frequency', 'is_peak_hour', 'is_active',
            'created_at', 'updated_at', 'line_details', 'bus_details',
            'driver_details', 'days_of_week_display'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'line_details', 'bus_details',
            'driver_details', 'days_of_week_display'
        ]
    
    def get_days_of_week_display(self, obj):
        return [obj.get_days_of_week_display(day) for day in obj.days_of_week]


class ScheduleCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Schedule
        fields = [
            'line', 'bus', 'driver', 'start_time', 'end_time',
            'days_of_week', 'frequency', 'is_peak_hour'
        ]


class ScheduleExceptionSerializer(BaseModelSerializer):
    schedule_details = ScheduleSerializer(source='schedule', read_only=True)
    
    class Meta:
        model = ScheduleException
        fields = [
            'id', 'schedule', 'date', 'is_cancelled', 'reason',
            'is_active', 'created_at', 'updated_at', 'schedule_details'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'schedule_details'
        ]


class ScheduleExceptionCreateSerializer(BaseModelSerializer):
    class Meta:
        model = ScheduleException
        fields = [
            'schedule', 'date', 'is_cancelled', 'reason'
        ]


class ScheduledTripSerializer(BaseModelSerializer):
    schedule_details = ScheduleSerializer(source='schedule', read_only=True)
    delay_status = serializers.SerializerMethodField()
    
    class Meta:
        model = ScheduledTrip
        fields = [
            'id', 'schedule', 'date', 'start_time', 'end_time',
            'status', 'tracking_session', 'actual_start_time',
            'actual_end_time', 'delay_minutes', 'notes', 'is_active',
            'created_at', 'updated_at', 'schedule_details', 'delay_status'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'schedule_details', 'delay_status'
        ]
    
    def get_delay_status(self, obj):
        if obj.delay_minutes == 0:
            return "on_time"
        elif obj.delay_minutes < 5:
            return "slight_delay"
        elif obj.delay_minutes < 15:
            return "moderate_delay"
        else:
            return "significant_delay"


class ScheduledTripCreateSerializer(BaseModelSerializer):
    class Meta:
        model = ScheduledTrip
        fields = [
            'schedule', 'date', 'start_time', 'end_time', 'notes'
        ]


class ScheduledTripUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = ScheduledTrip
        fields = [
            'status', 'tracking_session', 'actual_start_time',
            'actual_end_time', 'delay_minutes', 'notes'
        ]


class MaintenanceScheduleSerializer(BaseModelSerializer):
    bus_details = BusSerializer(source='bus', read_only=True)
    
    class Meta:
        model = MaintenanceSchedule
        fields = [
            'id', 'bus', 'start_date', 'end_date', 'maintenance_type',
            'description', 'is_completed', 'completed_at', 'notes',
            'is_active', 'created_at', 'updated_at', 'bus_details'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'bus_details'
        ]


class MaintenanceScheduleCreateSerializer(BaseModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = [
            'bus', 'start_date', 'end_date', 'maintenance_type',
            'description', 'notes'
        ]


class MaintenanceScheduleUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = [
            'end_date', 'maintenance_type', 'description',
            'is_completed', 'completed_at', 'notes'
        ]


class ScheduleCalendarSerializer(serializers.Serializer):
    date = serializers.DateField()
    day_name = serializers.CharField()
    trips = ScheduledTripSerializer(many=True)
    exceptions = ScheduleExceptionSerializer(many=True)
    maintenance = MaintenanceScheduleSerializer(many=True)
