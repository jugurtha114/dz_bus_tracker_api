"""
Serializers for the buses API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.api.v1.drivers.serializers import DriverSerializer
from apps.buses.models import Bus
from drf_spectacular.utils import extend_schema_field


class BusSerializer(BaseSerializer):
    """
    Serializer for buses.
    """
    driver_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bus
        fields = [
            'id', 'license_plate', 'driver', 'driver_details', 'model',
            'manufacturer', 'year', 'capacity', 'status', 'is_air_conditioned',
            'photo', 'features', 'description', 'is_active', 'is_approved',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

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


class BusBriefSerializer(BaseSerializer):
    """
    Brief serializer for buses.
    """
    class Meta:
        model = Bus
        fields = ['id', 'bus_number', 'license_plate', 'status']
