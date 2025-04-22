from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from apps.authentication.serializers import UserSerializer
from apps.lines.serializers import LineSerializer, StopSerializer
from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest


class PassengerSerializer(BaseModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = Passenger
        fields = [
            'id', 'user', 'journey_count', 'notification_preferences',
            'home_location', 'work_location', 'is_active', 'created_at',
            'updated_at', 'user_details'
        ]
        read_only_fields = ['id', 'journey_count', 'created_at', 'updated_at', 'user_details']


class PassengerUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = Passenger
        fields = [
            'notification_preferences', 'home_location', 'work_location'
        ]


class SavedLocationSerializer(BaseModelSerializer):
    class Meta:
        model = SavedLocation
        fields = [
            'id', 'passenger', 'name', 'latitude', 'longitude',
            'address', 'is_favorite', 'is_active', 'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SavedLocationCreateSerializer(BaseModelSerializer):
    class Meta:
        model = SavedLocation
        fields = [
            'name', 'latitude', 'longitude', 'address', 'is_favorite'
        ]


class TripHistorySerializer(BaseModelSerializer):
    line_details = LineSerializer(source='line', read_only=True)
    start_stop_details = StopSerializer(source='start_stop', read_only=True)
    end_stop_details = StopSerializer(source='end_stop', read_only=True)
    
    class Meta:
        model = TripHistory
        fields = [
            'id', 'passenger', 'line', 'start_stop', 'end_stop',
            'start_time', 'end_time', 'status', 'is_active', 'created_at',
            'updated_at', 'line_details', 'start_stop_details', 'end_stop_details'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'line_details', 
                           'start_stop_details', 'end_stop_details']


class TripHistoryCreateSerializer(BaseModelSerializer):
    class Meta:
        model = TripHistory
        fields = [
            'line', 'start_stop', 'end_stop', 'start_time'
        ]


class TripHistoryUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = TripHistory
        fields = [
            'end_time', 'status'
        ]


class FeedbackRequestSerializer(BaseModelSerializer):
    passenger_name = serializers.CharField(source='passenger.user.get_full_name', read_only=True)
    line_name = serializers.CharField(source='line.name', read_only=True)
    
    class Meta:
        model = FeedbackRequest
        fields = [
            'id', 'passenger', 'trip', 'line', 'sent_at', 'expires_at',
            'is_completed', 'is_active', 'created_at', 'updated_at',
            'passenger_name', 'line_name'
        ]
        read_only_fields = ['id', 'sent_at', 'created_at', 'updated_at',
                           'passenger_name', 'line_name']


class NotificationPreferencesSerializer(serializers.Serializer):
    push_enabled = serializers.BooleanField(default=True)
    email_enabled = serializers.BooleanField(default=True)
    sms_enabled = serializers.BooleanField(default=False)
    eta_threshold = serializers.IntegerField(default=5, min_value=1, max_value=60)


class PassengerStatsSerializer(serializers.Serializer):
    total_trips = serializers.IntegerField()
    completed_trips = serializers.IntegerField()
    cancelled_trips = serializers.IntegerField()
    most_used_lines = serializers.ListField(child=serializers.DictField())
    most_used_stops = serializers.ListField(child=serializers.DictField())
    total_distance_traveled = serializers.FloatField()
    total_time_traveled = serializers.FloatField()
    first_trip_date = serializers.DateTimeField()
    last_trip_date = serializers.DateTimeField()
