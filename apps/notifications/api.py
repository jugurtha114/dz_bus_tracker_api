from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.base.api import BaseViewSet
from apps.core.base.permissions import IsAdmin, IsOwnerOrAdmin
from .models import Notification, NotificationPreference, PushToken, NotificationLog
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    NotificationCreateSerializer,
    NotificationPreferenceSerializer,
    NotificationPreferenceUpdateSerializer,
    PushTokenSerializer,
    PushTokenCreateSerializer,
    NotificationLogSerializer,
    BulkNotificationSerializer,
    MarkAsReadSerializer
)
from .selectors import (
    get_notification_by_id,
    get_notifications_for_user,
    get_unread_notifications_count,
    get_notification_preferences,
    get_notification_preference,
    get_push_tokens_for_user,
    get_push_token,
    get_notification_logs,
    get_notification_activity_summary,
    get_notification_delivery_stats,
    search_notifications,
    get_action_required_notifications
)
from .services import (
    create_notification,
    send_notification,
    mark_notification_as_read,
    mark_notifications_as_read,
    mark_all_as_read,
    update_notification_preferences,
    register_push_token,
    deactivate_push_token,
    create_bulk_notifications,
    cleanup_expired_notifications
)


class NotificationViewSet(BaseViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_create']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        elif self.action == 'create':
            return NotificationCreateSerializer
        elif self.action == 'bulk_create':
            return BulkNotificationSerializer
        elif self.action == 'mark_read':
            return MarkAsReadSerializer
        return NotificationSerializer
    
    def get_queryset(self):
        # Only return notifications for the current user unless admin
        if self.request.user.is_admin:
            return self.queryset
        
        return self.queryset.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        create_notification(
            user=serializer.validated_data['user'],
            notification_type=serializer.validated_data['type'],
            title=serializer.validated_data['title'],
            message=serializer.validated_data['message'],
            data=serializer.validated_data.get('data'),
            is_action_required=serializer.validated_data.get('is_action_required', False),
            action_url=serializer.validated_data.get('action_url', ''),
            expiration_date=serializer.validated_data.get('expiration_date')
        )
    
    @action(detail=False, methods=['get'])
    def my_notifications(self, request):
        is_read = request.query_params.get('is_read')
        notification_type = request.query_params.get('type')
        limit = request.query_params.get('limit')
        
        if is_read is not None:
            is_read = is_read.lower() == 'true'
        
        if limit:
            try:
                limit = int(limit)
            except ValueError:
                limit = None
        
        notifications = get_notifications_for_user(
            user_id=request.user.id,
            is_read=is_read,
            notification_type=notification_type,
            limit=limit
        )
        
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = NotificationListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = NotificationListSerializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        notification_type = request.query_params.get('type')
        
        count = get_unread_notifications_count(
            user_id=request.user.id,
            notification_type=notification_type
        )
        
        return Response({'count': count})
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        
        # Check if user is allowed to mark as read
        if notification.user != request.user and not request.user.is_admin:
            return Response(
                {'detail': 'You do not have permission to mark this notification as read.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        updated_notification = mark_notification_as_read(notification.id)
        
        return Response(NotificationSerializer(updated_notification).data)
    
    @action(detail=False, methods=['post'])
    def mark_multiple_read(self, request):
        serializer = MarkAsReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        notification_ids = serializer.validated_data['notification_ids']
        
        # Check if user is allowed to mark these notifications as read
        if not request.user.is_admin:
            # Filter to only include user's notifications
            notifications = Notification.objects.filter(
                id__in=notification_ids,
                user=request.user
            )
            notification_ids = [str(n.id) for n in notifications]
        
        updated_count = mark_notifications_as_read(notification_ids)
        
        return Response({'detail': f'Marked {updated_count} notifications as read.'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        updated_count = mark_all_as_read(request.user.id)
        
        return Response({'detail': f'Marked {updated_count} notifications as read.'})
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can create bulk notifications.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        created_count = create_bulk_notifications(
            user_ids=serializer.validated_data['user_ids'],
            notification_type=serializer.validated_data['type'],
            title=serializer.validated_data['title'],
            message=serializer.validated_data['message'],
            data=serializer.validated_data.get('data'),
            is_action_required=serializer.validated_data.get('is_action_required', False),
            action_url=serializer.validated_data.get('action_url', ''),
            expiration_date=serializer.validated_data.get('expiration_date'),
            send_push=serializer.validated_data.get('send_push', True),
            send_email=serializer.validated_data.get('send_email', False),
            send_sms=serializer.validated_data.get('send_sms', False)
        )
        
        return Response({'detail': f'Created {created_count} notifications.'})
    
    @action(detail=False, methods=['get'])
    def action_required(self, request):
        notifications = get_action_required_notifications(request.user.id)
        
        serializer = NotificationListSerializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def cleanup_expired(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can clean up expired notifications.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        days = request.data.get('days', 30)
        
        try:
            days = int(days)
        except ValueError:
            days = 30
        
        result = cleanup_expired_notifications(days=days)
        
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def activity_summary(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can view activity summary.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        days = request.query_params.get('days', 7)
        
        try:
            days = int(days)
        except ValueError:
            days = 7
        
        summary = get_notification_activity_summary(days=days)
        
        return Response(summary)
    
    @action(detail=False, methods=['get'])
    def delivery_stats(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can view delivery stats.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        days = request.query_params.get('days', 7)
        
        try:
            days = int(days)
        except ValueError:
            days = 7
        
        stats = get_notification_delivery_stats(days=days)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q')
        
        if not query:
            return Response(
                {'detail': 'Search query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notifications = search_notifications(request.user.id, query)
        
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = NotificationListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = NotificationListSerializer(notifications, many=True)
        return Response(serializer.data)


class NotificationPreferenceViewSet(BaseViewSet):
    queryset = NotificationPreference.objects.all()
    serializer_class = NotificationPreferenceSerializer
    
    def get_permissions(self):
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return NotificationPreferenceUpdateSerializer
        return NotificationPreferenceSerializer
    
    def get_queryset(self):
        # Only return preferences for the current user unless admin
        if self.request.user.is_admin:
            return self.queryset
        
        return self.queryset.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def my_preferences(self, request):
        preferences = get_notification_preferences(request.user.id)
        
        serializer = self.get_serializer(preferences, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['put'])
    def update_preference(self, request):
        notification_type = request.data.get('notification_type')
        
        if not notification_type:
            return Response(
                {'detail': 'Notification type is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = NotificationPreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        preference = update_notification_preferences(
            user_id=request.user.id,
            notification_type=notification_type,
            preferences=serializer.validated_data
        )
        
        return Response(NotificationPreferenceSerializer(preference).data)


class PushTokenViewSet(BaseViewSet):
    queryset = PushToken.objects.all()
    serializer_class = PushTokenSerializer
    
    def get_permissions(self):
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PushTokenCreateSerializer
        return PushTokenSerializer
    
    def get_queryset(self):
        # Only return tokens for the current user unless admin
        if self.request.user.is_admin:
            return self.queryset
        
        return self.queryset.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        register_push_token(
            user=self.request.user,
            token=serializer.validated_data['token'],
            device_type=serializer.validated_data['device_type'],
            device_name=serializer.validated_data.get('device_name', '')
        )
    
    @action(detail=False, methods=['get'])
    def my_tokens(self, request):
        tokens = get_push_tokens_for_user(request.user.id)
        
        serializer = self.get_serializer(tokens, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def deactivate(self, request):
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'detail': 'Token is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if token belongs to user
        push_token = get_push_token(token)
        
        if not push_token:
            return Response(
                {'detail': 'Token not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if push_token.user != request.user and not request.user.is_admin:
            return Response(
                {'detail': 'You do not have permission to deactivate this token.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        deactivated_token = deactivate_push_token(token)
        
        return Response(PushTokenSerializer(deactivated_token).data)


class NotificationLogViewSet(BaseViewSet):
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by notification
        notification_id = self.request.query_params.get('notification')
        if notification_id:
            queryset = queryset.filter(notification_id=notification_id)
        
        # Filter by method
        method = self.request.query_params.get('method')
        if method:
            queryset = queryset.filter(method=method)
        
        # Filter by success
        success = self.request.query_params.get('success')
        if success is not None:
            success = success.lower() == 'true'
            queryset = queryset.filter(success=success)
        
        return queryset.select_related('notification', 'notification__user')