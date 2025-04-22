from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsDriver, IsAdminOrDriver, IsOwnerOrAdmin
from .models import Driver, DriverApplication, DriverRating
from .serializers import (
    DriverSerializer,
    DriverCreateSerializer,
    DriverUpdateSerializer,
    DriverApplicationSerializer,
    DriverApplicationCreateSerializer,
    DriverApplicationActionSerializer,
    DriverRatingSerializer,
    DriverRatingCreateSerializer,
    DriverStatsSerializer
)
from .selectors import (
    get_driver_by_id,
    get_driver_for_user,
    get_active_drivers,
    get_drivers_by_verification_status,
    get_driver_ratings,
    filter_drivers
)
from .services import (
    create_driver,
    update_driver,
    verify_driver,
    create_driver_rating,
    deactivate_driver,
    reactivate_driver,
    get_driver_stats
)


class DriverViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    parser_classes = [MultiPartParser, FormParser]
    select_related_fields = ['user']
    prefetch_related_fields = ['ratings', 'buses']
    filterset_fields = ['is_active', 'is_verified']
    search_fields = ['user__first_name', 'user__last_name', 'id_number', 'license_number']
    
    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'ratings']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        elif self.action in ['verify', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DriverCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return DriverUpdateSerializer
        elif self.action == 'verify':
            return DriverApplicationActionSerializer
        elif self.action == 'rate':
            return DriverRatingCreateSerializer
        elif self.action == 'stats':
            return DriverStatsSerializer
        return DriverSerializer
    
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
        
        # If user is a driver, only show their own profile
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        create_driver(
            user=self.request.user,
            data=serializer.validated_data
        )
    
    def perform_update(self, serializer):
        update_driver(
            driver_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        driver = self.get_object()
        
        # Get the latest pending application
        application = driver.applications.filter(status='pending').order_by('-created_at').first()
        
        if not application:
            return Response(
                {'detail': 'No pending application found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        verified_application = verify_driver(
            application_id=application.id,
            admin_user=request.user,
            status=serializer.validated_data['status'],
            notes=serializer.validated_data.get('notes', ''),
            rejection_reason=serializer.validated_data.get('rejection_reason', '')
        )
        
        return Response(
            DriverApplicationSerializer(verified_application).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def rate(self, request, pk=None):
        driver = self.get_object()
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Set driver in validated data
        validated_data = serializer.validated_data.copy()
        validated_data['driver'] = driver
        
        rating = create_driver_rating(
            passenger=request.user,
            driver_id=driver.id,
            rating_data=validated_data
        )
        
        return Response(
            DriverRatingSerializer(rating).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def ratings(self, request, pk=None):
        driver = self.get_object()
        
        ratings = get_driver_ratings(driver.id)
        
        page = self.paginate_queryset(ratings)
        if page is not None:
            serializer = DriverRatingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = DriverRatingSerializer(ratings, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        driver = self.get_object()
        
        reason = request.data.get('reason', '')
        
        deactivated_driver = deactivate_driver(
            driver_id=driver.id,
            reason=reason
        )
        
        return Response(
            DriverSerializer(deactivated_driver).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        driver = self.get_object()
        
        reactivated_driver = reactivate_driver(driver_id=driver.id)
        
        return Response(
            DriverSerializer(reactivated_driver).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        driver = self.get_object()
        
        stats = get_driver_stats(driver.id)
        
        serializer = self.get_serializer(data=stats)
        serializer.is_valid()  # Already formatted correctly, no need to raise_exception
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        if not request.user.is_driver:
            return Response(
                {'detail': 'You are not registered as a driver.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        driver = get_driver_for_user(request.user)
        
        if not driver:
            return Response(
                {'detail': 'Driver profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_verification(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can access this endpoint.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        drivers = get_drivers_by_verification_status('pending')
        
        page = self.paginate_queryset(drivers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(drivers, many=True)
        return Response(serializer.data)


class DriverApplicationViewSet(BaseViewSet):
    queryset = DriverApplication.objects.all()
    serializer_class = DriverApplicationSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated(), IsDriver()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DriverApplicationCreateSerializer
        return DriverApplicationSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by driver
        driver_id = self.request.query_params.get('driver')
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # If user is a driver, only show their own applications
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(driver__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        # If driver is creating their own application
        if self.request.user.is_driver:
            driver = get_driver_for_user(self.request.user)
            if not driver:
                return Response(
                    {'detail': 'Driver profile not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if there's a pending application
            if driver.applications.filter(status='pending').exists():
                return Response(
                    {'detail': 'You already have a pending application.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer.save(driver=driver)
        else:
            serializer.save()


class DriverRatingViewSet(BaseViewSet):
    queryset = DriverRating.objects.all()
    serializer_class = DriverRatingSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return DriverRatingCreateSerializer
        return DriverRatingSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by driver
        driver_id = self.request.query_params.get('driver')
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        
        # Filter by passenger
        passenger_id = self.request.query_params.get('passenger')
        if passenger_id:
            queryset = queryset.filter(passenger_id=passenger_id)
        
        # Filter by rating
        rating = self.request.query_params.get('rating')
        if rating:
            queryset = queryset.filter(rating=rating)
        
        # If user is a driver, only show ratings for them
        if self.request.user.is_driver and not self.request.user.is_admin:
            queryset = queryset.filter(driver__user=self.request.user)
        
        # If regular user, only show their own ratings or anonymous ratings
        if not (self.request.user.is_admin or self.request.user.is_driver):
            queryset = queryset.filter(
                passenger=self.request.user
            )
        
        return queryset
    
    def perform_create(self, serializer):
        create_driver_rating(
            passenger=self.request.user,
            driver_id=serializer.validated_data['driver'].id,
            rating_data=serializer.validated_data
        )