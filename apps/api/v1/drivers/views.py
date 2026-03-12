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
        if self.action in ['reapply']:
            return [IsAuthenticated()]
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
        driver.refresh_from_db()
        return Response(DriverSerializer(driver, context={'request': request}).data)

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
        driver.refresh_from_db()
        return Response(DriverSerializer(driver, context={'request': request}).data)

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

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reapply(self, request, pk=None):
        """
        Allow a rejected driver to re-apply for approval.

        Only the driver themselves (or an admin) can trigger this action.
        The driver must currently be in 'rejected' status.
        """
        driver = self.get_object()

        # Only the driver themselves or staff can re-apply
        if driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You can only re-apply for your own driver application.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Only rejected drivers can re-apply
        if driver.status != 'rejected':
            return Response(
                {
                    'detail': (
                        f'Only rejected drivers can re-apply. '
                        f'Current status: {driver.status}'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Reset status to pending and clear the rejection reason
        from django.utils import timezone
        driver.status = 'pending'
        driver.rejection_reason = ''
        driver.status_changed_at = timezone.now()
        driver.save(update_fields=['status', 'rejection_reason', 'status_changed_at'])

        # Notify admin users asynchronously
        try:
            from apps.notifications.services import NotificationService
            from apps.accounts.models import User
            admins = User.objects.filter(user_type='admin', is_active=True)
            for admin in admins:
                NotificationService.create_notification(
                    user_id=str(admin.id),
                    notification_type='driver_application',
                    title='Driver Re-application',
                    message=f'Driver {driver.user.get_full_name() or driver.user.email} has re-applied.',
                    data={'driver_id': str(driver.id)},
                )
        except Exception:
            # Notification failure must not roll back the reapply
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to notify admins about driver re-application {driver.id}"
            )

        driver.refresh_from_db()
        serializer = DriverSerializer(driver)
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
