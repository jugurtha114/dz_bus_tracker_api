"""
Views for the notifications app.
"""
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.api.pagination import StandardResultsSetPagination
from apps.api.permissions import IsOwnerOrReadOnly
from .models import DeviceToken, Notification, NotificationPreference, NotificationSchedule
from .serializers import (
    DeviceTokenSerializer,
    NotificationSerializer,
    NotificationCreateSerializer,
    NotificationMarkReadSerializer,
    NotificationPreferenceSerializer,
    NotificationScheduleSerializer,
    ArrivalNotificationSerializer,
    DelayNotificationSerializer,
)
from .services import NotificationService, DeviceTokenService
from .filters import NotificationFilter


class DeviceTokenViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing device tokens.
    """
    serializer_class = DeviceTokenSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get device tokens for the current user."""
        return DeviceToken.objects.filter(
            user=self.request.user,
            is_active=True
        ).order_by('-last_used')
    
    def perform_create(self, serializer):
        """Register a device token."""
        DeviceTokenService.register_device(
            user_id=str(self.request.user.id),
            token=serializer.validated_data['token'],
            device_type=serializer.validated_data['device_type']
        )
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a device token."""
        token = self.get_object()
        DeviceTokenService.deactivate_device(
            user_id=str(request.user.id),
            token=token.token
        )
        return Response(
            {'message': _('Device token deactivated successfully.')},
            status=status.HTTP_200_OK
        )


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_class = NotificationFilter
    
    def get_queryset(self):
        """Get notifications for the current user."""
        return Notification.objects.filter(
            user=self.request.user
        ).select_related('user').order_by('-created_at')
    
    def get_serializer_class(self):
        """Get appropriate serializer class."""
        if self.action == 'create':
            return NotificationCreateSerializer
        return NotificationSerializer
    
    def perform_create(self, serializer):
        """Create a notification."""
        NotificationService.create_notification(
            user_id=str(self.request.user.id),
            **serializer.validated_data
        )
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        updated = NotificationService.mark_as_read(str(notification.id))
        serializer = self.get_serializer(updated)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        notification_ids = serializer.validated_data.get('notification_ids', [])
        
        if notification_ids:
            # Mark specific notifications as read
            for notification_id in notification_ids:
                try:
                    NotificationService.mark_as_read(str(notification_id))
                except Exception:
                    pass  # Skip invalid IDs
            
            count = len(notification_ids)
        else:
            # Mark all as read
            count = NotificationService.mark_all_as_read(str(request.user.id))
        
        return Response(
            {'message': _(f'{count} notifications marked as read.')},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        return Response({'count': count})
    
    @action(detail=False, methods=['post'])
    def schedule_arrival(self, request):
        """Schedule a notification for bus arrival."""
        serializer = ArrivalNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        scheduled = NotificationService.schedule_arrival_notification(
            user_id=str(request.user.id),
            **serializer.validated_data
        )
        
        if scheduled:
            return Response(
                NotificationScheduleSerializer(scheduled).data,
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {'message': _('Notification sent immediately (arrival is too soon to schedule).')},
                status=status.HTTP_200_OK
            )


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notification preferences.
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get preferences for the current user."""
        return NotificationPreference.objects.filter(
            user=self.request.user
        ).prefetch_related('favorite_stops', 'favorite_lines')
    
    def perform_create(self, serializer):
        """Create or update notification preferences."""
        notification_type = serializer.validated_data['notification_type']
        
        # Extract the many-to-many fields
        favorite_stop_ids = serializer.validated_data.pop('favorite_stop_ids', [])
        favorite_line_ids = serializer.validated_data.pop('favorite_line_ids', [])
        
        # Update preferences
        preference = NotificationService.update_preferences(
            user_id=str(self.request.user.id),
            notification_type=notification_type,
            enabled=serializer.validated_data.get('enabled'),
            channels=serializer.validated_data.get('channels'),
            minutes_before_arrival=serializer.validated_data.get('minutes_before_arrival'),
            quiet_hours_start=serializer.validated_data.get('quiet_hours_start'),
            quiet_hours_end=serializer.validated_data.get('quiet_hours_end'),
            favorite_stops=favorite_stop_ids,
            favorite_lines=favorite_line_ids
        )
        
        # Update the instance for response
        serializer.instance = preference
    
    def perform_update(self, serializer):
        """Update notification preferences."""
        # Extract the many-to-many fields
        favorite_stop_ids = serializer.validated_data.pop('favorite_stop_ids', [])
        favorite_line_ids = serializer.validated_data.pop('favorite_line_ids', [])
        
        # Update preferences
        preference = NotificationService.update_preferences(
            user_id=str(self.request.user.id),
            notification_type=serializer.instance.notification_type,
            enabled=serializer.validated_data.get('enabled'),
            channels=serializer.validated_data.get('channels'),
            minutes_before_arrival=serializer.validated_data.get('minutes_before_arrival'),
            quiet_hours_start=serializer.validated_data.get('quiet_hours_start'),
            quiet_hours_end=serializer.validated_data.get('quiet_hours_end'),
            favorite_stops=favorite_stop_ids if 'favorite_stop_ids' in self.request.data else None,
            favorite_lines=favorite_line_ids if 'favorite_line_ids' in self.request.data else None
        )
        
        # Update the instance for response
        serializer.instance = preference
    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get preference by notification type."""
        notification_type = request.query_params.get('type')
        
        if not notification_type:
            return Response(
                {'error': _('Notification type is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            preference = NotificationPreference.objects.get(
                user=request.user,
                notification_type=notification_type
            )
            serializer = self.get_serializer(preference)
            return Response(serializer.data)
        except NotificationPreference.DoesNotExist:
            return Response(
                {'message': _('No preference found for this notification type.')},
                status=status.HTTP_404_NOT_FOUND
            )


class NotificationScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing scheduled notifications.
    """
    serializer_class = NotificationScheduleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get scheduled notifications for the current user."""
        return NotificationSchedule.objects.filter(
            user=self.request.user,
            is_sent=False
        ).select_related(
            'user', 'bus', 'stop', 'line', 'trip'
        ).order_by('scheduled_for')
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a scheduled notification."""
        schedule = self.get_object()
        schedule.is_sent = True  # Mark as sent to prevent sending
        schedule.error = "Cancelled by user"
        schedule.save()
        
        return Response(
            {'message': _('Scheduled notification cancelled.')},
            status=status.HTTP_200_OK
        )


class SystemNotificationViewSet(viewsets.ViewSet):
    """
    ViewSet for system-wide notifications (admin only).
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def notify_delay(self, request):
        """Send delay notifications for a bus/line."""
        if not request.user.is_staff:
            return Response(
                {'error': _('Only staff can send system notifications.')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = DelayNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        NotificationService.notify_delay(**serializer.validated_data)
        
        return Response(
            {'message': _('Delay notifications sent successfully.')},
            status=status.HTTP_200_OK
        )