"""
Serializers for the buses API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.api.v1.drivers.serializers import DriverSerializer
from apps.buses.models import Bus, BusLocation


class BusLocationSerializer(BaseSerializer):
    """
    Serializer for bus locations.
    """

    class Meta:
        model = BusLocation
        fields = [
            'id', 'bus', 'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy', 'is_tracking_active', 'passenger_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BusLocationCreateSerializer(BaseSerializer):
    """
    Serializer for creating bus locations.
    """

    class Meta:
        model = BusLocation
        fields = [
            'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy', 'passenger_count',
        ]


class BusSerializer(BaseSerializer):
    """
    Serializer for buses.
    """
    driver_details = serializers.SerializerMethodField(read_only=True)
    current_location = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bus
        fields = [
            'id', 'license_plate', 'driver', 'driver_details', 'model',
            'manufacturer', 'year', 'capacity', 'status', 'is_air_conditioned',
            'photo', 'features', 'description', 'is_active', 'is_approved',
            'current_location', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_driver_details(self, obj):
        """
        Get driver details if expand_driver is True.
        """
        expand = self.context.get('request').query_params.get('expand_driver', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return DriverSerializer(obj.driver).data
        return None

    def get_current_location(self, obj):
        """
        Get current location if expand_location is True.
        """
        expand = self.context.get('request').query_params.get('expand_location', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            try:
                location = obj.locations.latest('created_at')
                return BusLocationSerializer(location).data
            except BusLocation.DoesNotExist:
                return None
        return None


class BusCreateSerializer(BaseSerializer):
    """
    Serializer for creating buses.
    """

    class Meta:
        model = Bus
        fields = [
            'license_plate', 'driver', 'model', 'manufacturer', 'year',
            'capacity', 'is_air_conditioned', 'photo', 'features', 'description',
        ]


class BusUpdateSerializer(BaseSerializer):
    """
    Serializer for updating buses.
    """

    class Meta:
        model = Bus
        fields = [
            'model', 'manufacturer', 'year', 'capacity', 'status',
            'is_air_conditioned', 'photo', 'features', 'description',
            'is_active',
        ]


class BusApproveSerializer(serializers.Serializer):
    """
    Serializer for approving buses.
    """
    approve = serializers.BooleanField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class BusLocationUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating bus location.
    """
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    altitude = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    speed = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    heading = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    accuracy = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    passenger_count = serializers.IntegerField(required=False, min_value=0)


class PassengerCountUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating passenger count.
    """
    count = serializers.IntegerField(min_value=0)


class BusBriefSerializer(BaseSerializer):
    """
    Brief serializer for buses.
    """
    class Meta:
        model = Bus
        fields = ['id', 'bus_number', 'license_plate', 'status']