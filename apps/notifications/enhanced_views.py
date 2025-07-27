"""
Enhanced API views for professional notification management.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet
from apps.core.permissions import IsAdmin, IsOwnerOrReadOnly

from .models import DeviceToken, Notification, NotificationPreference
from .enhanced_services import EnhancedNotificationService, EnhancedDeviceTokenService
from .monitoring import NotificationMonitor
from .templates import NotificationTemplateFactory
from .firebase import FCMService, FCMPriority
from .enhanced_tasks import (
    send_bulk_notification_task,
    test_push_notification,
    cleanup_invalid_tokens,
    notification_health_check
)

# Import existing serializers and add new ones
from .serializers import (
    DeviceTokenCreateSerializer,
    DeviceTokenSerializer,
    NotificationSerializer,
    NotificationCreateSerializer
)


class EnhancedDeviceTokenViewSet(BaseModelViewSet):
    """Enhanced API endpoint for device token management."""
    
    queryset = DeviceToken.objects.all()
    serializer_class = DeviceTokenSerializer
    service_class = EnhancedDeviceTokenService
    
    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ['register', 'update_token', 'test_token']:
            return [IsAuthenticated()]
        if self.action in ['health_check', 'cleanup_invalid']:
            return [IsAdmin()]
        return [IsAuthenticated(), IsOwnerOrReadOnly()]
    
    def get_serializer_class(self):
        """Get serializer based on action."""
        if self.action in ['create', 'register']:
            return DeviceTokenCreateSerializer
        return DeviceTokenSerializer
    
    def get_queryset(self):
        """Filter tokens based on user permissions."""
        queryset = super().get_queryset()
        
        # Regular users can only see their own tokens
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(user=user)
        
        return queryset.select_related('user')
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        """
        Register a new device token with enhanced validation.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            device_token = EnhancedDeviceTokenService.register_device_token(
                user_id=str(request.user.id),
                token=serializer.validated_data['token'],
                device_type=serializer.validated_data['device_type'],
                device_info=request.data.get('device_info'),
                app_version=request.data.get('app_version'),
                os_version=request.data.get('os_version')
            )
            
            response_serializer = DeviceTokenSerializer(device_token)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def test_token(self, request, pk=None):
        """
        Send a test notification to a specific device token.
        """
        device_token = self.get_object()
        
        # Ensure user owns this token or is admin
        if device_token.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Send test notification
        task = test_push_notification.delay(
            user_id=str(device_token.user.id),
            message=request.data.get('message', 'Test notification from DZ Bus Tracker')
        )
        
        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Test notification queued'
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def cleanup_invalid(self, request):
        """
        Cleanup invalid device tokens.
        """
        task = cleanup_invalid_tokens.delay(
            batch_size=request.data.get('batch_size', 100)
        )
        
        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Token cleanup started'
        })
    
    @action(detail=False, methods=['get'])
    def my_tokens(self, request):
        """
        Get current user's device tokens.
        """
        tokens = EnhancedDeviceTokenService.get_user_active_tokens(str(request.user.id))
        serializer = DeviceTokenSerializer(tokens, many=True)
        
        return Response({
            'tokens': serializer.data,
            'count': len(tokens)
        })


class EnhancedNotificationViewSet(BaseModelViewSet):
    """Enhanced API endpoint for notifications."""
    
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    
    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ['send_notification', 'send_bulk', 'get_templates']:
            return [IsAdmin()]
        if self.action in ['system_health', 'stats']:
            return [IsAdminUser()]
        return [IsAuthenticated(), IsOwnerOrReadOnly()]
    
    def get_queryset(self):
        """Filter notifications based on user permissions."""
        queryset = super().get_queryset()
        
        # Regular users can only see their own notifications
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(user=user)
        
        return queryset.select_related('user').order_by('-created_at')
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def send_notification(self, request):
        """
        Send a notification to specific users using templates.
        """
        try:
            # Extract parameters
            user_ids = request.data.get('user_ids', [])
            template_type = request.data.get('template_type')
            channels = request.data.get('channels', ['in_app'])
            priority = request.data.get('priority', 'normal')
            template_kwargs = request.data.get('template_data', {})
            
            # Validate inputs
            if not user_ids:
                return Response(
                    {'error': 'user_ids is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not template_type:
                return Response(
                    {'error': 'template_type is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate template exists
            template = NotificationTemplateFactory.get_template(template_type)
            if not template:
                return Response(
                    {'error': f'Unknown template type: {template_type}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Send notifications
            if len(user_ids) == 1:
                # Single notification
                result = EnhancedNotificationService.send_notification(
                    user_id=user_ids[0],
                    template_type=template_type,
                    channels=channels,
                    priority=FCMPriority.HIGH if priority == 'high' else FCMPriority.NORMAL,
                    **template_kwargs
                )
                
                return Response(result)
            else:
                # Bulk notification
                result = EnhancedNotificationService.send_bulk_notification(
                    user_ids=user_ids,
                    template_type=template_type,
                    channels=channels,
                    priority=FCMPriority.HIGH if priority == 'high' else FCMPriority.NORMAL,
                    **template_kwargs
                )
                
                return Response(result)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def send_bulk(self, request):
        """
        Send bulk notifications efficiently using Celery.
        """
        try:
            user_ids = request.data.get('user_ids', [])
            template_type = request.data.get('template_type')
            channels = request.data.get('channels', ['in_app'])
            priority = request.data.get('priority', 'normal')
            template_kwargs = request.data.get('template_data', {})
            
            if not user_ids or not template_type:
                return Response(
                    {'error': 'user_ids and template_type are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Queue bulk notification task
            task = send_bulk_notification_task.delay(
                user_ids=user_ids,
                template_type=template_type,
                channels=channels,
                priority=priority,
                **template_kwargs
            )
            
            return Response({
                'success': True,
                'task_id': task.id,
                'user_count': len(user_ids),
                'message': 'Bulk notification queued'
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def get_templates(self, request):
        """
        Get available notification templates.
        """
        templates = NotificationTemplateFactory.get_available_templates()
        
        # Get template details
        template_details = []
        for template_type in templates:
            template = NotificationTemplateFactory.get_template(template_type)
            if template:
                template_details.append({
                    'type': template_type,
                    'channel_id': template.get_channel_id(),
                    'icon': template.get_icon(),
                    'color': template.get_color()
                })
        
        return Response({
            'templates': template_details,
            'count': len(template_details)
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def system_health(self, request):
        """
        Get notification system health status.
        """
        try:
            refresh = request.query_params.get('refresh', 'false').lower() == 'true'
            health = NotificationMonitor.get_system_health(refresh=refresh)
            
            return Response({
                'status': health.status.value,
                'score': health.score,
                'summary': health.summary,
                'timestamp': health.timestamp.isoformat(),
                'metrics': [
                    {
                        'name': metric.name,
                        'value': metric.value,
                        'status': metric.status.value,
                        'message': metric.message,
                        'details': metric.details
                    }
                    for metric in health.metrics
                ]
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def stats(self, request):
        """
        Get notification system statistics.
        """
        try:
            hours = int(request.query_params.get('hours', 24))
            stats = NotificationMonitor.get_notification_stats(hours=hours)
            
            return Response(stats)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def fcm_metrics(self, request):
        """
        Get Firebase Cloud Messaging metrics.
        """
        try:
            metrics = NotificationMonitor.get_fcm_metrics()
            return Response(metrics)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def my_analytics(self, request):
        """
        Get notification analytics for the current user.
        """
        try:
            days = int(request.query_params.get('days', 30))
            analytics = NotificationMonitor.get_user_notification_analytics(
                user_id=str(request.user.id),
                days=days
            )
            
            return Response(analytics)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def health_check_task(self, request):
        """
        Run notification system health check as a background task.
        """
        task = notification_health_check.delay()
        
        return Response({
            'success': True,
            'task_id': task.id,
            'message': 'Health check started'
        })


class NotificationPreferenceViewSet(BaseModelViewSet):
    """API endpoint for notification preferences."""
    
    queryset = NotificationPreference.objects.all()
    
    def get_permissions(self):
        """Get permissions based on action."""
        return [IsAuthenticated(), IsOwnerOrReadOnly()]
    
    def get_queryset(self):
        """Filter preferences based on user permissions."""
        queryset = super().get_queryset()
        
        # Regular users can only see their own preferences
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(user=user)
        
        return queryset.select_related('user').prefetch_related(
            'favorite_stops', 'favorite_lines'
        )
    
    @action(detail=False, methods=['get', 'patch'])
    def my_preferences(self, request):
        """
        Get or update current user's notification preferences.
        """
        if request.method == 'GET':
            preferences = self.get_queryset().filter(user=request.user)
            
            # Group by notification type
            prefs_by_type = {}
            for pref in preferences:
                prefs_by_type[pref.notification_type] = {
                    'enabled': pref.enabled,
                    'channels': pref.channels,
                    'minutes_before_arrival': pref.minutes_before_arrival,
                    'quiet_hours_start': pref.quiet_hours_start.isoformat() if pref.quiet_hours_start else None,
                    'quiet_hours_end': pref.quiet_hours_end.isoformat() if pref.quiet_hours_end else None,
                    'favorite_stops': [str(stop.id) for stop in pref.favorite_stops.all()],
                    'favorite_lines': [str(line.id) for line in pref.favorite_lines.all()]
                }
            
            return Response(prefs_by_type)
            
        elif request.method == 'PATCH':
            # Update preferences
            updates = request.data
            results = {}
            
            for notification_type, settings in updates.items():
                try:
                    from .services import NotificationService
                    
                    preference = NotificationService.update_preferences(
                        user_id=str(request.user.id),
                        notification_type=notification_type,
                        **settings
                    )
                    
                    results[notification_type] = {
                        'success': True,
                        'enabled': preference.enabled
                    }
                    
                except Exception as e:
                    results[notification_type] = {
                        'success': False,
                        'error': str(e)
                    }
            
            return Response(results)