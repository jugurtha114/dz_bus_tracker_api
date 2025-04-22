from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsDriver, IsAdminOrDriver, IsOwnerOrAdmin
from .models import Bus, BusPhoto, BusVerification, BusMaintenance
from .serializers import (
    BusSerializer,
    BusCreateSerializer,
    BusUpdateSerializer,
    BusPhotoSerializer,
    BusVerificationSerializer,
    BusVerificationActionSerializer,
    BusMaintenanceSerializer,
    BusStatusSerializer
)
from .selectors import (
    get_bus_by_id,
    get_buses_for_driver,
    get_active_buses,
    get_buses_by_verification_status,
    filter_buses
)
from .services import (
    create_bus,
    update_bus,
    add_bus_photo,
    verify_bus,
    add_maintenance_record,
    deactivate_bus,
    reactivate_bus,
    get_bus_status
)


class BusViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Bus.objects.all()
    serializer_class = BusSerializer
    select_related_fields = ['driver', 'driver__user']
    prefetch_related_fields = ['photos', 'verifications']
    filterset_fields = ['driver', 'is_active', 'is_verified']
    search_fields = ['matricule', 'brand', 'model']
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update']:
            return [permissions.IsAuthenticated(), IsAdminOrDriver()]
        elif self.action in ['verify', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        elif self.action in ['add_photo', 'maintenance']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BusCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BusUpdateSerializer
        elif self.action == 'add_photo':
            return BusPhotoSerializer
        elif self.action == 'verify':
            return BusVerificationActionSerializer
        elif self.action == 'maintenance':
            return BusMaintenanceSerializer
        elif self.action == 'status':
            return BusStatusSerializer
        return BusSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by verified status
        verified = self.request.query_params.get('verified')
        if verified is not None:
            verified = verified.lower() == 'true'
            queryset = queryset.filter(is_verified=verified)
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            active = active.lower() == 'true'
            queryset = queryset.filter(is_active=active)
        
        # Filter by driver
        driver_id = self.request.query_params.get('driver_id')
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        
        # If user is a driver, only show their buses
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(driver__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        if self.request.user.is_driver:
            from apps.drivers.selectors import get_driver_for_user
            driver = get_driver_for_user(self.request.user)
            if not driver:
                return Response(
                    {'detail': 'Driver profile not found.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Use the driver's own profile
            data = serializer.validated_data.copy()
            data['driver'] = driver
        else:
            data = serializer.validated_data
        
        create_bus(
            driver=data['driver'],
            data=data,
            photos=serializer.validated_data.pop('photos', []),
            photo_types=serializer.validated_data.pop('photo_types', [])
        )
    
    def perform_update(self, serializer):
        update_bus(
            bus_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def add_photo(self, request, pk=None):
        """
        Add a photo to a bus.
        """
        bus = self.get_object()
        
        # Check if user is allowed
        if request.user.is_driver and bus.driver.user != request.user:
            return Response(
                {'detail': 'You can only add photos to your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        photo = request.data.get('photo')
        photo_type = request.data.get('photo_type', 'exterior')
        description = request.data.get('description', '')
        
        if not photo:
            return Response(
                {'detail': 'Photo is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        bus_photo = add_bus_photo(
            bus_id=bus.id,
            photo=photo,
            photo_type=photo_type,
            description=description
        )
        
        serializer = BusPhotoSerializer(bus_photo)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """
        Verify or reject a bus.
        """
        bus = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        verification = verify_bus(
            bus_id=bus.id,
            admin_user=request.user,
            status=serializer.validated_data['status'],
            notes=serializer.validated_data.get('notes', ''),
            rejection_reason=serializer.validated_data.get('rejection_reason', '')
        )
        
        return Response(
            BusVerificationSerializer(verification).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def maintenance(self, request, pk=None):
        """
        Add a maintenance record to a bus.
        """
        bus = self.get_object()
        
        # Check if user is allowed
        if request.user.is_driver and bus.driver.user != request.user:
            return Response(
                {'detail': 'You can only add maintenance records to your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        maintenance = add_maintenance_record(
            bus_id=bus.id,
            data=serializer.validated_data
        )
        
        return Response(
            BusMaintenanceSerializer(maintenance).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate a bus.
        """
        bus = self.get_object()
        
        # Check if user is allowed
        if request.user.is_driver and bus.driver.user != request.user:
            return Response(
                {'detail': 'You can only deactivate your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reason = request.data.get('reason', '')
        
        deactivated_bus = deactivate_bus(
            bus_id=bus.id,
            reason=reason
        )
        
        return Response(
            BusSerializer(deactivated_bus).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """
        Reactivate a bus.
        """
        bus = self.get_object()
        
        # Check if user is allowed
        if request.user.is_driver and bus.driver.user != request.user:
            return Response(
                {'detail': 'You can only reactivate your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reactivated_bus = reactivate_bus(bus_id=bus.id)
        
        return Response(
            BusSerializer(reactivated_bus).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Get the current status of a bus.
        """
        bus = self.get_object()
        
        status_data = get_bus_status(bus.id)
        
        serializer = self.get_serializer(data=status_data)
        serializer.is_valid()  # Already formatted correctly, no need to raise_exception
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def photos(self, request, pk=None):
        """
        Get all photos for a bus.
        """
        bus = self.get_object()
        
        photos = bus.photos.all()
        serializer = BusPhotoSerializer(photos, many=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_driver(self, request):
        """
        Get all buses for the current driver.
        """
        if not request.user.is_driver:
            return Response(
                {'detail': 'Only drivers can access this endpoint.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.drivers.selectors import get_driver_for_user
        driver = get_driver_for_user(request.user)
        
        if not driver:
            return Response(
                {'detail': 'Driver profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        buses = get_buses_for_driver(driver.id)
        
        page = self.paginate_queryset(buses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(buses, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_verification(self, request):
        """
        Get all buses pending verification.
        """
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can access this endpoint.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        buses = get_buses_by_verification_status('pending')
        
        page = self.paginate_queryset(buses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(buses, many=True)
        return Response(serializer.data)


class BusPhotoViewSet(BaseViewSet):
    queryset = BusPhoto.objects.all()
    serializer_class = BusPhotoSerializer
    parser_classes = [MultiPartParser, FormParser]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by photo type
        photo_type = self.request.query_params.get('photo_type')
        if photo_type:
            queryset = queryset.filter(photo_type=photo_type)
        
        # If user is a driver, only show photos of their buses
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(bus__driver__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        # Check if the user owns the bus
        bus = serializer.validated_data.get('bus')
        
        if self.request.user.is_driver and bus.driver.user != self.request.user:
            return Response(
                {'detail': 'You can only add photos to your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer.save()


class BusVerificationViewSet(BaseViewSet):
    queryset = BusVerification.objects.all()
    serializer_class = BusVerificationSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # If user is a driver, only show verifications of their buses
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(bus__driver__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        # Set verified_by to current user
        serializer.save(verified_by=self.request.user)


class BusMaintenanceViewSet(BaseViewSet):
    queryset = BusMaintenance.objects.all()
    serializer_class = BusMaintenanceSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by maintenance type
        maintenance_type = self.request.query_params.get('maintenance_type')
        if maintenance_type:
            queryset = queryset.filter(maintenance_type=maintenance_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # If user is a driver, only show maintenance records of their buses
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(bus__driver__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        # Check if the user owns the bus
        bus = serializer.validated_data.get('bus')
        
        if self.request.user.is_driver and bus.driver.user != self.request.user:
            return Response(
                {'detail': 'You can only add maintenance records to your own buses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer.save()