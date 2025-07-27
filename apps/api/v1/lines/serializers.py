"""
Serializers for the lines API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.lines.models import Line, LineStop, Schedule, Stop
from drf_spectacular.utils import extend_schema_field


class StopSerializer(BaseSerializer):
    """
    Serializer for stops.
    """
    class Meta:
        model = Stop
        fields = [
            'id', 'name', 'latitude', 'longitude', 'address',
            'is_active', 'description', 'features', 'photo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StopCreateSerializer(BaseSerializer):
    """
    Serializer for creating stops.
    """
    class Meta:
        model = Stop
        fields = [
            'name', 'latitude', 'longitude', 'address',
            'description', 'features', 'photo',
        ]


class StopUpdateSerializer(BaseSerializer):
    """
    Serializer for updating stops.
    """
    class Meta:
        model = Stop
        fields = [
            'name', 'latitude', 'longitude', 'address',
            'is_active', 'description', 'features', 'photo',
        ]


class LineStopSerializer(BaseSerializer):
    """
    Serializer for line stops.
    """
    stop_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LineStop
        fields = [
            'id', 'line', 'stop', 'stop_details', 'order',
            'distance_from_previous', 'average_time_from_previous',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(dict)
    def get_stop_details(self, obj):
        """
        Get stop details if expand_stop is True.
        """
        expand = self.context.get('request').query_params.get('expand_stop', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return StopSerializer(obj.stop).data
        return None


class LineStopCreateSerializer(BaseSerializer):
    """
    Serializer for creating line stops.
    """
    class Meta:
        model = LineStop
        fields = [
            'stop', 'order', 'distance_from_previous',
            'average_time_from_previous',
        ]


class ScheduleSerializer(BaseSerializer):
    """
    Serializer for schedules.
    """
    class Meta:
        model = Schedule
        fields = [
            'id', 'line', 'day_of_week', 'start_time', 'end_time',
            'is_active', 'frequency_minutes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ScheduleCreateSerializer(BaseSerializer):
    """
    Serializer for creating schedules.
    """
    class Meta:
        model = Schedule
        fields = [
            'day_of_week', 'start_time', 'end_time',
            'frequency_minutes',
        ]


class LineSerializer(BaseSerializer):
    """
    Serializer for lines.
    """
    stops = serializers.SerializerMethodField(read_only=True)
    schedules = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Line
        fields = [
            'id', 'name', 'code', 'description', 'is_active',
            'color', 'frequency', 'stops', 'schedules',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(list)
    def get_stops(self, obj):
        """
        Get stops for this line if expand_stops is True.
        """
        expand = self.context.get('request').query_params.get('expand_stops', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            line_stops = obj.line_stops.all().order_by('order')
            return LineStopSerializer(
                line_stops,
                many=True,
                context=self.context
            ).data
        return None

    @extend_schema_field(list)
    def get_schedules(self, obj):
        """
        Get schedules for this line if expand_schedules is True.
        """
        expand = self.context.get('request').query_params.get('expand_schedules', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            schedules = obj.schedules.all().order_by('day_of_week', 'start_time')
            return ScheduleSerializer(schedules, many=True).data
        return None


class LineCreateSerializer(BaseSerializer):
    """
    Serializer for creating lines.
    """
    class Meta:
        model = Line
        fields = [
            'name', 'code', 'description', 'color', 'frequency',
        ]


class LineUpdateSerializer(BaseSerializer):
    """
    Serializer for updating lines.
    """
    class Meta:
        model = Line
        fields = [
            'name', 'description', 'is_active', 'color', 'frequency',
        ]


class AddStopToLineSerializer(serializers.Serializer):
    """
    Serializer for adding a stop to a line.
    """
    stop_id = serializers.UUIDField(required=True)
    order = serializers.IntegerField(required=True, min_value=0)
    distance_from_previous = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )
    average_time_from_previous = serializers.IntegerField(required=False)


class RemoveStopFromLineSerializer(serializers.Serializer):
    """
    Serializer for removing a stop from a line.
    """
    stop_id = serializers.UUIDField(required=True)


class UpdateStopOrderSerializer(serializers.Serializer):
    """
    Serializer for updating a stop's order in a line.
    """
    stop_id = serializers.UUIDField(required=True)
    new_order = serializers.IntegerField(required=True, min_value=0)


class LineBriefSerializer(BaseSerializer):
    """
    Brief serializer for lines.
    """
    class Meta:
        model = Line
        fields = ['id', 'name', 'code', 'is_active']


class StopBriefSerializer(BaseSerializer):
    """
    Brief serializer for stops.
    """
    class Meta:
        model = Stop
        fields = ['id', 'name', 'latitude', 'longitude']