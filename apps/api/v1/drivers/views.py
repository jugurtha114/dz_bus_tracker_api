"""
Views for the drivers API.
"""
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.services import UserService
from apps.api.viewsets import BaseModelViewSet, ReadOnlyModelViewSet
from apps.core.permissions import IsAdmin, IsDriverOrAdmin, IsOwnerOrReadOnly
from apps.drivers.models import Driver, DriverRating
from apps.drivers.services import DriverRatingService, DriverService

from .filters import DriverFilter, DriverRatingFilter
from .serializers import (
    DriverApproveSerializer,
    DriverAvailabilitySerializer,
    DriverCreateSerializer,
    DriverRatingCreateSerializer,
    DriverRatingSerializer,
    DriverRegistrationSerializer,
    DriverSerializer,
    DriverUpdateSerializer,
)


class DriverViewSet(BaseModelViewSet):
    """
    API endpoint for drivers.
    """
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    filterset_class = DriverFilter
    service_class = DriverService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['register']:
            return [AllowAny()]
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsDriverOrAdmin()]
        if self.action in ['approve', 'reject']:
            return [IsAdmin()]
        if self.action in ['update_availability']:
            return [IsOwnerOrReadOnly()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return DriverCreateSerializer
        if self.action in ['update', 'partial_update']:
            return DriverUpdateSerializer
        if self.action == 'register':
            return DriverRegistrationSerializer
        if self.action in ['approve', 'reject']:
            return DriverApproveSerializer
        if self.action == 'update_availability':
            return DriverAvailabilitySerializer
        return DriverSerializer

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def register(self, request):
        """
        Register a new driver.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract user and driver data
        user_data = {
            'email': serializer.validated_data.pop('email'),
            'password': serializer.validated_data.pop('password'),
            'first_name': serializer.validated_data.pop('first_name'),
            'last_name': serializer.validated_data.pop('last_name'),
            'phone_number': serializer.validated_data.get('phone_number'),
            'user_type': 'driver',
        }

        driver_data = serializer.validated_data

        # Create user
        user = UserService.create_user(**user_data)

        # Create driver
        driver = DriverService.create_driver(
            user_id=user.id,
            **driver_data
        )

        # Schedule driver application processing
        from tasks.drivers import process_driver_application
        process_driver_application.delay(driver.id)

        response_serializer = DriverSerializer(driver)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve a driver.
        """
        driver = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        DriverService.approve_driver(driver.id)
        return Response({'detail': 'Driver approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject a driver.
        """
        driver = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        DriverService.reject_driver(
            driver_id=driver.id,
            rejection_reason=serializer.validated_data.get('rejection_reason', '')
        )

        return Response({'detail': 'Driver rejected'})

    @action(detail=True, methods=['post'])
    def update_availability(self, request, pk=None):
        """
        Update driver availability.
        """
        driver = self.get_object()

        # Ensure the driver is updating their own availability
        if driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to update this driver\'s availability'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        DriverService.update_availability(
            driver_id=driver.id,
            is_available=serializer.validated_data['is_available']
        )

        return Response({'detail': 'Availability updated'})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """
        Get the current driver's profile.
        """
        try:
            driver = Driver.objects.get(user=request.user)
            serializer = self.get_serializer(driver)
            return Response(serializer.data)
        except Driver.DoesNotExist:
            return Response(
                {'detail': 'Driver profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'])
    def ratings(self, request, pk=None):
        """
        Get ratings for a driver.
        """
        driver = self.get_object()

        # Get ratings for this driver
        ratings = DriverRating.objects.filter(driver=driver).order_by('-created_at')

        # Apply filtering if needed
        filter_backend = DriverRatingFilter()
        ratings = filter_backend.filter_queryset(request, ratings, self)

        # Apply pagination
        page = self.paginate_queryset(ratings)
        if page is not None:
            serializer = DriverRatingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DriverRatingSerializer(ratings, many=True)
        return Response(serializer.data)


class DriverRatingViewSet(BaseModelViewSet):
    """
    API endpoint for driver ratings.
    """
    queryset = DriverRating.objects.all()
    serializer_class = DriverRatingSerializer
    filterset_class = DriverRatingFilter
    service_class = DriverRatingService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsOwnerOrReadOnly()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return DriverRatingCreateSerializer
        return DriverRatingSerializer

    def perform_create(self, serializer):
        """
        Create a driver rating.
        """
        driver_id = self.kwargs.get('driver_pk')
        if not driver_id:
            return Response(
                {'detail': 'Driver ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        DriverRatingService.rate_driver(
            driver_id=driver_id,
            user_id=self.request.user.id,
            rating=serializer.validated_data['rating'],
            comment=serializer.validated_data.get('comment', '')
        )