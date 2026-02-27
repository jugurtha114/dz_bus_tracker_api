"""
Serializers for the tracking API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.api.v1.buses.serializers import BusSerializer
from apps.api.v1.drivers.serializers import DriverSerializer
from apps.api.v1.lines.serializers import LineSerializer, StopSerializer
from drf_spectacular.utils import extend_schema_field
from apps.tracking.models import (
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


class BusLineSerializer(BaseSerializer):
    """
    Serializer for bus-line assignments.
    """
    bus_details = serializers.SerializerMethodField(read_only=True)
    line_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BusLine
        fields = [
            'id', 'bus', 'bus_details', 'line', 'line_details',
            'is_active', 'tracking_status', 'trip_id', 'start_time',
            'end_time', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(dict)
    def get_bus_details(self, obj):
        """
        Get bus details if expand_bus is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_bus', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return BusSerializer(obj.bus).data
        return None

    @extend_schema_field(dict)
    def get_line_details(self, obj):
        """
        Get line details if expand_line is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_line', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return LineSerializer(obj.line).data
        return None


class BusLineCreateSerializer(BaseSerializer):
    """
    Serializer for creating bus-line assignments.
    """
    class Meta:
        model = BusLine
        fields = ['bus', 'line']


class LocationUpdateSerializer(BaseSerializer):
    """
    Serializer for location updates.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'id', 'bus', 'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy', 'trip_id', 'nearest_stop',
            'distance_to_stop', 'line', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LocationUpdateCreateSerializer(BaseSerializer):
    """
    Serializer for creating location updates.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy',
        ]


class PassengerCountSerializer(BaseSerializer):
    """
    Serializer for passenger counts.
    """
    class Meta:
        model = PassengerCount
        fields = [
            'id', 'bus', 'count', 'capacity', 'occupancy_rate',
            'trip_id', 'stop', 'line', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'occupancy_rate']


class PassengerCountCreateSerializer(BaseSerializer):
    """
    Serializer for creating passenger counts.
    """
    class Meta:
        model = PassengerCount
        fields = ['count', 'stop']


class WaitingPassengersSerializer(BaseSerializer):
    """
    Serializer for waiting passengers.
    """
    stop_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WaitingPassengers
        fields = [
            'id', 'stop', 'stop_details', 'line', 'count',
            'reported_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(dict)
    def get_stop_details(self, obj):
        """
        Get stop details if expand_stop is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_stop', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return StopSerializer(obj.stop).data
        return None


class WaitingPassengersCreateSerializer(BaseSerializer):
    """
    Serializer for creating waiting passengers.
    """
    class Meta:
        model = WaitingPassengers
        fields = ['stop', 'line', 'count']


class TripSerializer(BaseSerializer):
    """
    Serializer for trips.
    """
    bus_details = serializers.SerializerMethodField(read_only=True)
    driver_details = serializers.SerializerMethodField(read_only=True)
    line_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'bus', 'bus_details', 'driver', 'driver_details',
            'line', 'line_details', 'start_time', 'end_time',
            'start_stop', 'end_stop', 'is_completed', 'distance',
            'average_speed', 'max_passengers', 'total_stops',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'is_completed', 'distance', 'average_speed',
            'max_passengers', 'total_stops', 'created_at', 'updated_at',
        ]

    @extend_schema_field(dict)
    def get_bus_details(self, obj):
        """
        Get bus details if expand_bus is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_bus', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return BusSerializer(obj.bus).data
        return None

    @extend_schema_field(dict)
    def get_driver_details(self, obj):
        """
        Get driver details if expand_driver is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_driver', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return DriverSerializer(obj.driver).data
        return None

    @extend_schema_field(dict)
    def get_line_details(self, obj):
        """
        Get line details if expand_line is True.
        """
        request = self.context.get('request')
        if request:
            expand = request.query_params.get('expand_line', False)
            if expand and expand.lower() in ['true', '1', 'yes']:
                return LineSerializer(obj.line).data
        return None


class TripCreateSerializer(BaseSerializer):
    """
    Serializer for creating trips.
    """
    class Meta:
        model = Trip
        fields = [
            'bus', 'driver', 'line', 'start_time',
            'start_stop', 'notes',
        ]


class TripUpdateSerializer(BaseSerializer):
    """
    Serializer for updating trips.
    """
    class Meta:
        model = Trip
        fields = [
            'end_time', 'end_stop', 'notes',
        ]


class AnomalySerializer(BaseSerializer):
    """
    Serializer for anomalies.
    """
    class Meta:
        model = Anomaly
        fields = [
            'id', 'bus', 'trip', 'type', 'description', 'severity',
            'location_latitude', 'location_longitude', 'resolved',
            'resolved_at', 'resolution_notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AnomalyCreateSerializer(BaseSerializer):
    """
    Serializer for creating anomalies.
    """
    class Meta:
        model = Anomaly
        fields = [
            'type', 'description', 'severity',
            'location_latitude', 'location_longitude',
        ]


class AnomalyResolveSerializer(serializers.Serializer):
    """
    Serializer for resolving anomalies.
    """
    resolution_notes = serializers.CharField(required=False, allow_blank=True)


class StartTrackingSerializer(serializers.Serializer):
    """
    Serializer for starting tracking.
    """
    line_id = serializers.UUIDField(required=True)


class StopTrackingSerializer(serializers.Serializer):
    """
    Serializer for stopping tracking.
    """
    pass


class EstimateArrivalTimeSerializer(serializers.Serializer):
    """
    Serializer for estimating arrival time.
    """
    stop_id = serializers.UUIDField(required=True)


class TripBriefSerializer(BaseSerializer):
    """
    Brief serializer for trips.
    """
    bus_number = serializers.CharField(source='bus.bus_number', read_only=True)
    line_name = serializers.CharField(source='line.name', read_only=True)
    
    class Meta:
        model = Trip
        fields = ['id', 'bus_number', 'line_name', 'start_time', 'end_time']


class BusWaitingListSerializer(BaseSerializer):
    """
    Serializer for bus waiting lists.
    """
    bus_details = serializers.SerializerMethodField(read_only=True)
    stop_details = serializers.SerializerMethodField(read_only=True)
    user_details = serializers.SerializerMethodField(read_only=True)
    waiting_duration = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BusWaitingList
        fields = [
            'id', 'bus', 'bus_details', 'stop', 'stop_details', 
            'user', 'user_details', 'joined_at', 'estimated_arrival',
            'is_active', 'notified_on_arrival', 'left_at', 'waiting_duration',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'joined_at', 'created_at', 'updated_at']

    @extend_schema_field(dict)
    def get_bus_details(self, obj):
        """Get bus details if expand_bus is True."""
        expand = self.context.get('request').query_params.get('expand_bus', False) if self.context.get('request') else False
        if expand and expand.lower() in ['true', '1', 'yes']:
            return BusSerializer(obj.bus).data
        return None

    @extend_schema_field(dict)
    def get_stop_details(self, obj):
        """Get stop details if expand_stop is True."""
        expand = self.context.get('request').query_params.get('expand_stop', False) if self.context.get('request') else False
        if expand and expand.lower() in ['true', '1', 'yes']:
            return StopSerializer(obj.stop).data
        return None

    @extend_schema_field(dict)
    def get_user_details(self, obj):
        """Get basic user details."""
        from apps.api.v1.accounts.serializers import UserSerializer
        return {
            'id': str(obj.user.id),
            'full_name': obj.user.get_full_name(),
            'first_name': obj.user.first_name
        }

    @extend_schema_field(int)
    def get_waiting_duration(self, obj):
        """Get waiting duration in minutes."""
        if obj.is_active:
            from django.utils import timezone
            duration = timezone.now() - obj.joined_at
            return int(duration.total_seconds() / 60)
        elif obj.left_at:
            duration = obj.left_at - obj.joined_at
            return int(duration.total_seconds() / 60)
        return 0


class BusWaitingListCreateSerializer(BaseSerializer):
    """
    Serializer for creating bus waiting list entries.
    """
    class Meta:
        model = BusWaitingList
        fields = ['bus', 'stop']


class ReputationScoreSerializer(BaseSerializer):
    """
    Serializer for reputation scores.
    """
    accuracy_rate = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = ReputationScore
        fields = [
            'id', 'user', 'total_reports', 'correct_reports', 
            'accuracy_rate', 'reputation_level', 'trust_multiplier',
            'last_updated', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'accuracy_rate', 'created_at', 'updated_at']

    @extend_schema_field(float)
    def get_accuracy_rate(self, obj):
        """Get accuracy rate as percentage."""
        return obj.accuracy_rate


class WaitingCountReportSerializer(BaseSerializer):
    """
    Serializer for waiting count reports.
    """
    reporter_details = serializers.SerializerMethodField(read_only=True)
    stop_details = serializers.SerializerMethodField(read_only=True)
    bus_details = serializers.SerializerMethodField(read_only=True)
    distance_from_stop = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WaitingCountReport
        fields = [
            'id', 'stop', 'stop_details', 'bus', 'bus_details', 'line',
            'reported_count', 'reporter', 'reporter_details', 'confidence_level',
            'confidence_score', 'is_verified', 'verification_status',
            'verified_by', 'actual_count', 'verified_at', 'location_verified',
            'reporter_latitude', 'reporter_longitude', 'distance_from_stop',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'confidence_score', 'is_verified', 'verification_status',
            'verified_by', 'verified_at', 'location_verified',
            'distance_from_stop', 'created_at', 'updated_at'
        ]

    @extend_schema_field(dict)
    def get_reporter_details(self, obj):
        """Get basic reporter details."""
        return {
            'id': str(obj.reporter.id),
            'full_name': obj.reporter.get_full_name(),
            'reputation_level': getattr(obj.reporter.reputation_score, 'reputation_level', 'bronze')
        }

    @extend_schema_field(dict)
    def get_stop_details(self, obj):
        """Get stop details if expand_stop is True."""
        expand = self.context.get('request').query_params.get('expand_stop', False) if self.context.get('request') else False
        if expand and expand.lower() in ['true', '1', 'yes']:
            return StopSerializer(obj.stop).data
        return None

    @extend_schema_field(dict)
    def get_bus_details(self, obj):
        """Get bus details if expand_bus is True."""
        expand = self.context.get('request').query_params.get('expand_bus', False) if self.context.get('request') else False
        if expand and expand.lower() in ['true', '1', 'yes']:
            return BusSerializer(obj.bus).data if obj.bus else None
        return None

    @extend_schema_field(float)
    def get_distance_from_stop(self, obj):
        """Calculate distance from reporter location to stop."""
        if obj.reporter_latitude and obj.reporter_longitude:
            from apps.core.utils.geo import calculate_distance
            return calculate_distance(
                float(obj.reporter_latitude),
                float(obj.reporter_longitude),
                float(obj.stop.latitude),
                float(obj.stop.longitude)
            )
        return None


class WaitingCountReportCreateSerializer(BaseSerializer):
    """
    Serializer for creating waiting count reports.
    """
    reporter_latitude = serializers.DecimalField(
        max_digits=10, 
        decimal_places=7,
        required=False,
        help_text="Reporter's current latitude for location verification"
    )
    reporter_longitude = serializers.DecimalField(
        max_digits=10, 
        decimal_places=7,
        required=False,
        help_text="Reporter's current longitude for location verification"
    )

    class Meta:
        model = WaitingCountReport
        fields = [
            'stop', 'bus', 'line', 'reported_count', 'confidence_level',
            'reporter_latitude', 'reporter_longitude'
        ]

    def validate(self, data):
        """Validate the report data."""
        # Ensure either bus or line is provided
        if not data.get('bus') and not data.get('line'):
            raise serializers.ValidationError(
                "Either 'bus' or 'line' must be specified"
            )
        
        # Validate reported count is reasonable
        if data.get('reported_count', 0) > 200:
            raise serializers.ValidationError(
                "Reported count seems unreasonably high"
            )
        
        return data


class WaitingCountReportVerifySerializer(serializers.Serializer):
    """
    Serializer for verifying waiting count reports.
    """
    actual_count = serializers.IntegerField(
        min_value=0,
        max_value=200,
        help_text="Actual number of people waiting as observed by driver"
    )
    verification_status = serializers.ChoiceField(
        choices=WaitingCountReport.VERIFICATION_STATUS,
        help_text="Driver's assessment of the report accuracy"
    )
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Optional notes about the verification"
    )


class VirtualCurrencySerializer(BaseSerializer):
    """
    Serializer for virtual currency.
    """
    class Meta:
        model = VirtualCurrency
        fields = [
            'id', 'user', 'balance', 'lifetime_earned', 'lifetime_spent',
            'last_transaction', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CurrencyTransactionSerializer(BaseSerializer):
    """
    Serializer for currency transactions.
    """
    class Meta:
        model = CurrencyTransaction
        fields = [
            'id', 'user', 'amount', 'transaction_type', 'description',
            'balance_after', 'related_report', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class WaitingListSummarySerializer(serializers.Serializer):
    """
    Serializer for waiting list summaries.
    """
    bus_id = serializers.UUIDField()
    bus_license_plate = serializers.CharField()
    stop_id = serializers.UUIDField()
    stop_name = serializers.CharField()
    waiting_count = serializers.IntegerField()
    latest_report_count = serializers.IntegerField()
    latest_report_time = serializers.DateTimeField(allow_null=True)
    estimated_arrival = serializers.DateTimeField(allow_null=True)
    confidence_score = serializers.FloatField()


class JoinWaitingListSerializer(serializers.Serializer):
    """
    Serializer for joining a waiting list.
    """
    bus_id = serializers.UUIDField(help_text="ID of the bus to wait for")
    stop_id = serializers.UUIDField(help_text="ID of the stop to wait at")


class LeaveWaitingListSerializer(serializers.Serializer):
    """
    Serializer for leaving a waiting list.
    """
    waiting_list_id = serializers.UUIDField(help_text="ID of the waiting list entry")
    reason = serializers.ChoiceField(
        choices=[
            ('boarded', 'Boarded the bus'),
            ('gave_up', 'Gave up waiting'),
            ('other_transport', 'Found alternative transport'),
            ('other', 'Other reason')
        ],
        required=False,
        help_text="Reason for leaving the waiting list"
    )


# Driver Performance & Premium Features Serializers

class DriverPerformanceScoreSerializer(BaseSerializer):
    """
    Serializer for driver performance scores.
    """
    driver_name = serializers.SerializerMethodField(read_only=True)
    driver_email = serializers.SerializerMethodField(read_only=True)
    on_time_percentage = serializers.SerializerMethodField(read_only=True)
    performance_level_display = serializers.CharField(
        source='get_performance_level_display', 
        read_only=True
    )

    class Meta:
        model = DriverPerformanceScore
        fields = [
            'id', 'driver', 'driver_name', 'driver_email', 'total_trips',
            'on_time_trips', 'on_time_percentage', 'performance_level',
            'performance_level_display', 'safety_score', 'passenger_rating',
            'fuel_efficiency_score', 'report_verification_accuracy',
            'current_streak', 'best_streak', 'last_updated',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'driver_name', 'driver_email', 'on_time_percentage',
            'performance_level_display', 'last_updated', 'created_at', 'updated_at'
        ]

    @extend_schema_field(str)
    def get_driver_name(self, obj):
        """Get driver's full name."""
        return obj.driver.user.get_full_name() or obj.driver.user.email

    @extend_schema_field(str)
    def get_driver_email(self, obj):
        """Get driver's email."""
        return obj.driver.user.email

    @extend_schema_field(float)
    def get_on_time_percentage(self, obj):
        """Get on-time performance percentage."""
        return obj.on_time_percentage


class PremiumFeatureSerializer(BaseSerializer):
    """
    Serializer for premium features.
    """
    feature_type_display = serializers.CharField(
        source='get_feature_type_display', 
        read_only=True
    )
    target_users_display = serializers.CharField(
        source='get_target_users_display', 
        read_only=True
    )
    required_level_display = serializers.CharField(
        source='get_required_level_display', 
        read_only=True
    )

    class Meta:
        model = PremiumFeature
        fields = [
            'id', 'name', 'feature_type', 'feature_type_display',
            'description', 'cost_coins', 'duration_days', 'target_users',
            'target_users_display', 'required_level', 'required_level_display',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'feature_type_display', 'target_users_display',
            'required_level_display', 'created_at', 'updated_at'
        ]


class UserPremiumFeatureSerializer(BaseSerializer):
    """
    Serializer for user's purchased premium features.
    """
    feature_details = PremiumFeatureSerializer(source='feature', read_only=True)
    user_name = serializers.SerializerMethodField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_remaining = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserPremiumFeature
        fields = [
            'id', 'user', 'user_name', 'feature', 'feature_details',
            'purchased_at', 'expires_at', 'is_active', 'is_expired',
            'coins_spent', 'days_remaining', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user_name', 'feature_details', 'is_expired',
            'days_remaining', 'created_at', 'updated_at'
        ]

    @extend_schema_field(str)
    def get_user_name(self, obj):
        """Get user's name or email."""
        return obj.user.get_full_name() or obj.user.email

    @extend_schema_field(int)
    def get_days_remaining(self, obj):
        """Get days remaining before expiration."""
        if obj.is_expired:
            return 0
        from django.utils import timezone
        delta = obj.expires_at - timezone.now()
        return max(0, delta.days)


class PurchasePremiumFeatureSerializer(serializers.Serializer):
    """
    Serializer for purchasing premium features.
    """
    feature_id = serializers.UUIDField(help_text="ID of the premium feature to purchase")

    def validate_feature_id(self, value):
        """Validate that the feature exists and is active."""
        try:
            feature = PremiumFeature.objects.get(id=value)
            if not feature.is_active:
                raise serializers.ValidationError("This feature is not available for purchase")
            return value
        except PremiumFeature.DoesNotExist:
            raise serializers.ValidationError("Premium feature not found")


class DriverCurrencyTransactionSerializer(BaseSerializer):
    """
    Serializer for driver currency transactions with additional context.
    """
    user_name = serializers.SerializerMethodField(read_only=True)
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display', 
        read_only=True
    )
    amount_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CurrencyTransaction
        fields = [
            'id', 'user', 'user_name', 'amount', 'amount_display',
            'transaction_type', 'transaction_type_display', 'description',
            'balance_after', 'related_report', 'metadata', 'created_at'
        ]
        read_only_fields = [
            'id', 'user_name', 'amount_display', 'transaction_type_display', 'created_at'
        ]

    @extend_schema_field(str)
    def get_user_name(self, obj):
        """Get user's name or email."""
        return obj.user.get_full_name() or obj.user.email

    @extend_schema_field(str)
    def get_amount_display(self, obj):
        """Get formatted amount with sign."""
        sign = "+" if obj.amount >= 0 else ""
        return f"{sign}{obj.amount}"


class DriverStatsSerializer(serializers.Serializer):
    """
    Serializer for driver statistics dashboard.
    """
    performance_score = DriverPerformanceScoreSerializer(read_only=True)
    virtual_currency = VirtualCurrencySerializer(read_only=True)
    active_premium_features = UserPremiumFeatureSerializer(many=True, read_only=True)
    recent_transactions = DriverCurrencyTransactionSerializer(many=True, read_only=True)
    available_features = PremiumFeatureSerializer(many=True, read_only=True)
    
    # Summary stats
    total_earnings_this_month = serializers.IntegerField(read_only=True)
    rank_position = serializers.IntegerField(read_only=True)
    achievements_count = serializers.IntegerField(read_only=True)