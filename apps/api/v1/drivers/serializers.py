"""
Serializers for the drivers API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.api.v1.accounts.serializers import UserSerializer
from apps.drivers.models import Driver, DriverRating
from drf_spectacular.utils import extend_schema_field


class DriverRatingSerializer(BaseSerializer):
    """
    Serializer for driver ratings.
    """
    user_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DriverRating
        fields = [
            'id', 'driver', 'user', 'user_name', 'rating', 'comment',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(str)
    def get_user_name(self, obj):
        """
        Get user name.
        """
        if obj.user:
            if obj.user.get_full_name():
                return obj.user.get_full_name()
            return obj.user.email
        return None


class DriverRatingCreateSerializer(BaseSerializer):
    """
    Serializer for creating driver ratings.
    """

    class Meta:
        model = DriverRating
        fields = ['rating', 'comment']


class DriverSerializer(BaseSerializer):
    """
    Serializer for drivers.
    """
    user_details = serializers.SerializerMethodField(read_only=True)
    full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'user', 'user_details', 'full_name', 'phone_number',
            'id_card_number', 'id_card_photo', 'driver_license_number',
            'driver_license_photo', 'status', 'status_changed_at',
            'rejection_reason', 'years_of_experience', 'is_active',
            'is_available', 'rating', 'total_ratings', 'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'status_changed_at', 'rejection_reason',
            'rating', 'total_ratings', 'created_at', 'updated_at',
        ]

    @extend_schema_field(dict)
    def get_user_details(self, obj):
        """
        Get user details if expand_user is True.
        """
        request = self.context.get('request')
        if request and request.query_params.get('expand_user', '').lower() in ['true', '1', 'yes']:
            return UserSerializer(obj.user).data
        return None

    @extend_schema_field(str)
    def get_full_name(self, obj):
        """
        Get driver's full name.
        """
        return obj.user.get_full_name() or obj.user.email


class DriverCreateSerializer(BaseSerializer):
    """
    Serializer for creating drivers.
    """

    class Meta:
        model = Driver
        fields = [
            'user', 'phone_number', 'id_card_number', 'id_card_photo',
            'driver_license_number', 'driver_license_photo',
            'years_of_experience',
        ]


class DriverRegistrationSerializer(serializers.Serializer):
    """
    Serializer for driver registration.
    """
    # User details
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.CharField()

    # Driver details
    id_card_number = serializers.CharField()
    id_card_photo = serializers.ImageField()
    driver_license_number = serializers.CharField()
    driver_license_photo = serializers.ImageField()
    years_of_experience = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        """
        Validate that passwords match.
        """
        if attrs['password'] != attrs.pop('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        return attrs


class DriverUpdateSerializer(BaseSerializer):
    """
    Serializer for updating drivers.
    """

    class Meta:
        model = Driver
        fields = [
            'phone_number', 'id_card_photo', 'driver_license_photo',
            'years_of_experience', 'is_available',
        ]


class DriverApproveSerializer(serializers.Serializer):
    """
    Serializer for approving drivers.
    """
    approve = serializers.BooleanField(required=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class DriverAvailabilitySerializer(serializers.Serializer):
    """
    Serializer for updating driver availability.
    """
    is_available = serializers.BooleanField(required=True)