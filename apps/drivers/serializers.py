from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from apps.authentication.serializers import UserSerializer
from .models import Driver, DriverApplication, DriverRating


class DriverSerializer(BaseModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Driver
        fields = [
            'id', 'user', 'id_number', 'id_photo', 'license_number',
            'license_photo', 'is_verified', 'verification_date',
            'experience_years', 'date_of_birth', 'address',
            'emergency_contact', 'notes', 'metadata', 'is_active',
            'created_at', 'updated_at', 'user_details', 'full_name',
            'email', 'phone_number', 'average_rating'
        ]
        read_only_fields = [
            'id', 'is_verified', 'verification_date', 'created_at',
            'updated_at', 'user_details', 'full_name', 'email',
            'phone_number', 'average_rating'
        ]
    
    def get_average_rating(self, obj):
        ratings = obj.ratings.filter(is_active=True)
        if not ratings.exists():
            return None
        
        total = sum(rating.rating for rating in ratings)
        return total / ratings.count()


class DriverCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Driver
        fields = [
            'id', 'user', 'id_number', 'id_photo', 'license_number',
            'license_photo', 'experience_years', 'date_of_birth', 'address',
            'emergency_contact', 'notes', 'metadata'
        ]
        read_only_fields = ['id']
    
    def create(self, validated_data):
        driver = super().create(validated_data)
        
        # Create initial application
        DriverApplication.objects.create(
            driver=driver,
            status='pending'
        )
        
        return driver


class DriverUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = Driver
        fields = [
            'id_photo', 'license_photo', 'experience_years', 'date_of_birth',
            'address', 'emergency_contact', 'notes', 'metadata', 'is_active'
        ]


class DriverApplicationSerializer(BaseModelSerializer):
    driver_details = DriverSerializer(source='driver', read_only=True)
    reviewer_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    
    class Meta:
        model = DriverApplication
        fields = [
            'id', 'driver', 'status', 'reviewed_by', 'reviewed_at',
            'rejection_reason', 'notes', 'metadata', 'is_active',
            'created_at', 'updated_at', 'driver_details', 'reviewer_name'
        ]
        read_only_fields = [
            'id', 'driver', 'created_at', 'updated_at',
            'driver_details', 'reviewer_name'
        ]


class DriverApplicationCreateSerializer(BaseModelSerializer):
    class Meta:
        model = DriverApplication
        fields = [
            'driver', 'notes', 'metadata'
        ]


class DriverApplicationActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    notes = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        if attrs['status'] == 'rejected' and not attrs.get('rejection_reason'):
            raise serializers.ValidationError({"rejection_reason": "Rejection reason is required when rejecting an application."})
        return attrs


class DriverRatingSerializer(BaseModelSerializer):
    passenger_name = serializers.CharField(source='passenger.get_full_name', read_only=True)
    
    class Meta:
        model = DriverRating
        fields = [
            'id', 'driver', 'passenger', 'rating', 'comment', 'trip',
            'is_anonymous', 'created_at', 'updated_at', 'passenger_name'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'passenger_name'
        ]


class DriverRatingCreateSerializer(BaseModelSerializer):
    class Meta:
        model = DriverRating
        fields = [
            'driver', 'rating', 'comment', 'trip', 'is_anonymous'
        ]
    
    def validate(self, attrs):
        passenger = self.context['request'].user
        driver = attrs.get('driver')
        trip = attrs.get('trip')
        
        # Check if user has already rated this driver for this trip
        if trip and DriverRating.objects.filter(
            driver=driver,
            passenger=passenger,
            trip=trip
        ).exists():
            raise serializers.ValidationError("You have already rated this driver for this trip.")
        
        return attrs


class DriverStatsSerializer(serializers.Serializer):
    total_trips = serializers.IntegerField()
    total_distance = serializers.FloatField()
    active_since = serializers.DateTimeField()
    bus_count = serializers.IntegerField()
    verified_bus_count = serializers.IntegerField()
    average_rating = serializers.FloatField()
    total_ratings = serializers.IntegerField()
    completed_trips_last_month = serializers.IntegerField()
