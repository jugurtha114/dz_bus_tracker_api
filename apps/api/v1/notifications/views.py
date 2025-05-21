"""
Views for the notifications API.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet
from apps.core.permissions import IsAdmin, IsOwnerOrReadOnly
from apps.notifications.models import DeviceToken, Notification
from apps.notifications.services import DeviceTokenService, NotificationService

from .filters import DeviceTokenFilter, NotificationFilter
from .serializers import (
    DeviceTokenCreateSerializer,
    DeviceTokenSerializer,
    MarkAllAsReadSerializer,
    MarkAsReadSerializer,
    NotificationCreateSerializer,
    NotificationSerializer,
)


class NotificationViewSet(BaseModelViewSet):
    """
    API endpoint for notifications.
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    service_class = NotificationService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        if self.action in ['list', 'retrieve', 'mark_as_read', 'mark_all_as_read']:
            return [IsAuthenticated(), IsOwnerOrReadOnly()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return NotificationCreateSerializer
        if self.action == 'mark_as_read':
            return MarkAsReadSerializer
        if self.action == 'mark_all_as_read':
            return MarkAllAsReadSerializer
        return NotificationSerializer

    def get_queryset(self):
        """
        Filter notifications based on user and parameters.
        """
        queryset = super().get_queryset()

        # Regular users can only see their own notifications
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(user=user)
        else:
            # Admin can filter by user ID
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)

        # Filter by read status if provided
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read == 'true')

        # Filter by notification type if provided
        notification_type = self.request.query_params.get('notification_type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        # Filter by channel if provided
        channel = self.request.query_params.get('channel')
        if channel:
            queryset = queryset.filter(channel=channel)

        # Order by creation date, newest first
        return queryset.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Mark a notification as read.
        """
        notification = self.get_object()

        # Ensure the user owns this notification
        if notification.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to mark this notification as read'},
                status=status.HTTP_403_FORBIDDEN
            )

        NotificationService.mark_as_read(notification.id)

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """
        Mark all of the user's notifications as read.
        """
        count = NotificationService.mark_all_as_read(request.user.id)

        return Response({'detail': f'Marked {count} notifications as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """
        Get the count of unread notifications.
        """
        from apps.notifications.selectors import get_unread_notification_count
        count = get_unread_notification_count(request.user.id)

        return Response({'count': count})


class DeviceTokenViewSet(BaseModelViewSet):
    """
    API endpoint for device tokens.
    """
    queryset = DeviceToken.objects.all()
    serializer_class = DeviceTokenSerializer
    filterset_class = DeviceTokenFilter
    service_class = DeviceTokenService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['create', 'destroy', 'deactivate']:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return DeviceTokenCreateSerializer
        return DeviceTokenSerializer

    def get_queryset(self):
        """
        Filter device tokens based on user and parameters.
        """
        queryset = super().get_queryset()

        # Regular users can only see their own device tokens
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(user=user)
        else:
            # Admin can filter by user ID
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)

        # Filter by device type if provided
        device_type = self.request.query_params.get('device_type')
        if device_type:
            queryset = queryset.filter(device_type=device_type)

        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """
        Register a device token for the current user.
        """
        DeviceTokenService.register_device(
            user_id=self.request.user.id,
            **serializer.validated_data
        )

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate a device token.
        """
        device_token = self.get_object()

        # Ensure the user owns this device token
        if device_token.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to deactivate this device token'},
                status=status.HTTP_403_FORBIDDEN
            )

        DeviceTokenService.deactivate_device(
            user_id=device_token.user.id,
            token=device_token.token
        )

        return Response({'detail': 'Device token deactivated'})