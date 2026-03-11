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
        if self.action in ['list', 'retrieve', 'ratings']:
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
        if self.action in ['approve', 'reject']:
            return DriverApproveSerializer
        if self.action == 'update_availability':
            return DriverAvailabilitySerializer
        return DriverSerializer

    @action(detail=False, methods=['post'])
    def register(self, request):
        """
        Deprecated: Use /api/v1/accounts/register-driver/ instead.
        """
        return Response(
            {'detail': 'This endpoint is deprecated. Use /api/v1/accounts/register-driver/ instead.'},
            status=status.HTTP_410_GONE
        )

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

        updated_driver = DriverService.update_availability(
            driver_id=driver.id,
            is_available=serializer.validated_data['is_available']
        )
        # Refresh from DB to get latest state
        updated_driver.refresh_from_db()
        response_serializer = DriverSerializer(updated_driver)
        return Response(response_serializer.data)

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

    @action(detail=True, methods=['get', 'post'])
    def ratings(self, request, pk=None):
        """
        GET: Get ratings for a driver.
        POST: Submit a rating for a driver.
        """
        driver = self.get_object()

        if request.method == 'POST':
            serializer = DriverRatingCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            driver_rating = DriverRatingService.rate_driver(
                driver_id=str(driver.id),
                user_id=str(request.user.id),
                rating=serializer.validated_data['rating'],
                comment=serializer.validated_data.get('comment', '')
            )

            response_serializer = DriverRatingSerializer(driver_rating)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        # GET: list ratings
        ratings = DriverRating.objects.filter(driver=driver).order_by('-created_at')

        # Apply filtering via FilterSet
        filterset = DriverRatingFilter(request.query_params, queryset=ratings)
        if filterset.is_valid():
            ratings = filterset.qs

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
        driver = serializer.validated_data.get('driver')
        if not driver:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError({'driver': 'Driver is required'})

        DriverRatingService.rate_driver(
            driver_id=str(driver.id),
            user_id=str(self.request.user.id),
            rating=serializer.validated_data['rating'],
            comment=serializer.validated_data.get('comment', '')
        )
