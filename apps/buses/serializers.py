from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from apps.drivers.serializers import DriverSerializer
from .models import Bus, BusPhoto, BusVerification, BusMaintenance


class BusPhotoSerializer(BaseModelSerializer):
    class Meta:
        model = BusPhoto
        fields = ['id', 'bus', 'photo', 'photo_type', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class BusMaintenanceSerializer(BaseModelSerializer):
    class Meta:
        model = BusMaintenance
        fields = [
            'id', 'bus', 'maintenance_type', 'date', 'description',
            'cost', 'performed_by', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BusVerificationSerializer(BaseModelSerializer):
    class Meta:
        model = BusVerification
        fields = [
            'id', 'bus', 'verified_by', 'status', 'verification_date',
            'rejection_reason', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BusSerializer(BaseModelSerializer):
    photos = BusPhotoSerializer(many=True, read_only=True)
    driver_details = DriverSerializer(source='driver', read_only=True)
    is_tracking = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Bus
        fields = [
            'id', 'driver', 'matricule', 'brand', 'model', 'year',
            'capacity', 'description', 'is_verified', 'verification_date',
            'last_maintenance', 'next_maintenance', 'metadata',
            'is_active', 'created_at', 'updated_at', 'photos', 'driver_details',
            'is_tracking'
        ]
        read_only_fields = [
            'id', 'is_verified', 'verification_date', 'created_at', 'updated_at',
            'photos', 'driver_details', 'is_tracking'
        ]


class BusCreateSerializer(BaseModelSerializer):
    photos = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        write_only=True
    )
    photo_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = Bus
        fields = [
            'id', 'driver', 'matricule', 'brand', 'model', 'year',
            'capacity', 'description', 'photos', 'photo_types',
            'metadata'
        ]
        read_only_fields = ['id']
    
    def validate(self, attrs):
        photos = attrs.pop('photos', [])
        photo_types = attrs.pop('photo_types', [])
        
        # Ensure equal number of photos and photo types
        if photos and photo_types and len(photos) != len(photo_types):
            raise serializers.ValidationError("Number of photos and photo types must match")
        
        # Store for later use in create
        self.photos_data = zip(photos, photo_types) if photos and photo_types else []
        
        return attrs
    
    def create(self, validated_data):
        bus = Bus.objects.create(**validated_data)
        
        # Create photos if provided
        for photo, photo_type in self.photos_data:
            BusPhoto.objects.create(
                bus=bus,
                photo=photo,
                photo_type=photo_type
            )
        
        # Create initial verification record
        BusVerification.objects.create(
            bus=bus,
            status='pending'
        )
        
        return bus


class BusUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = Bus
        fields = [
            'brand', 'model', 'year', 'capacity', 'description',
            'next_maintenance', 'metadata', 'is_active'
        ]


class BusVerificationActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    notes = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        if attrs['status'] == 'rejected' and not attrs.get('rejection_reason'):
            raise serializers.ValidationError({"rejection_reason": "Rejection reason is required when rejecting a bus."})
        return attrs


class BusStatusSerializer(serializers.Serializer):
    bus_id = serializers.UUIDField()
    matricule = serializers.CharField()
    status = serializers.CharField()
    driver_id = serializers.UUIDField()
    driver_name = serializers.CharField()
    line_id = serializers.UUIDField(allow_null=True)
    line_name = serializers.CharField(allow_null=True)
    is_tracking = serializers.BooleanField()
    last_update = serializers.DateTimeField(allow_null=True)
