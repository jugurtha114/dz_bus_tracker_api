"""
Views for offline mode API endpoints.
"""
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.pagination import StandardResultsSetPagination
from apps.core.permissions import IsOwnerOrReadOnly

from .models import (
    CacheConfiguration,
    UserCache,
    CachedData,
    SyncQueue,
    OfflineLog,
)
from .serializers import (
    CacheConfigurationSerializer,
    UserCacheSerializer,
    CachedDataSerializer,
    SyncQueueSerializer,
    OfflineLogSerializer,
    SyncRequestSerializer,
    QueueActionSerializer,
    CacheStatisticsSerializer,
    DataRequestSerializer,
)
from .services import OfflineModeService


class CacheConfigurationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for cache configuration.
    
    Only staff can manage configurations.
    """
    queryset = CacheConfiguration.objects.all()
    serializer_class = CacheConfigurationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter to active configuration for non-staff."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active configuration."""
        config = self.get_queryset().filter(is_active=True).first()
        if config:
            serializer = self.get_serializer(config)
            return Response(serializer.data)
        return Response(
            {'detail': 'No active configuration found'},
            status=status.HTTP_404_NOT_FOUND
        )


class UserCacheViewSet(viewsets.GenericViewSet):
    """
    ViewSet for user cache management.
    """
    serializer_class = UserCacheSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        """Get user's cache."""
        return OfflineModeService.get_or_create_user_cache(
            str(self.request.user.id)
        )
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        """Get user's cache status."""
        cache = self.get_object()
        serializer = self.get_serializer(cache)
        return Response(serializer.data)
    
    @action(
        detail=False,
        methods=['post'],
        serializer_class=SyncRequestSerializer
    )
    def sync(self, request):
        """Sync user's offline data."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = OfflineModeService.sync_user_data(
            user_id=str(request.user.id),
            force=serializer.validated_data.get('force', False)
        )
        
        return Response(result)
    
    @action(detail=False, methods=['post'])
    def clear(self, request):
        """Clear user's cache."""
        success = OfflineModeService.clear_user_cache(
            str(request.user.id)
        )
        
        if success:
            return Response({'message': 'Cache cleared successfully'})
        
        return Response(
            {'error': 'Failed to clear cache'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get cache statistics."""
        stats = OfflineModeService.get_cache_statistics(
            str(request.user.id)
        )
        serializer = CacheStatisticsSerializer(data=stats)
        serializer.is_valid()
        return Response(serializer.data)


class CachedDataViewSet(viewsets.GenericViewSet):
    """
    ViewSet for accessing cached data.
    """
    serializer_class = CachedDataSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get user's cached data."""
        cache = OfflineModeService.get_or_create_user_cache(
            str(self.request.user.id)
        )
        return CachedData.objects.filter(user_cache=cache)
    
    @action(
        detail=False,
        methods=['post'],
        serializer_class=DataRequestSerializer
    )
    def get_data(self, request):
        """Get specific cached data."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type=serializer.validated_data['data_type'],
            data_id=serializer.validated_data.get('data_id')
        )
        
        if data is not None:
            return Response({'data': data})
        
        return Response(
            {'detail': 'Data not found in cache'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    @action(detail=False, methods=['get'])
    def lines(self, request):
        """Get cached lines."""
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type='line'
        )
        return Response({'results': data or []})
    
    @action(detail=False, methods=['get'])
    def stops(self, request):
        """Get cached stops."""
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type='stop'
        )
        return Response({'results': data or []})
    
    @action(detail=False, methods=['get'])
    def schedules(self, request):
        """Get cached schedules."""
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type='schedule'
        )
        return Response({'results': data or []})
    
    @action(detail=False, methods=['get'])
    def buses(self, request):
        """Get cached buses."""
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type='bus'
        )
        return Response({'results': data or []})
    
    @action(detail=False, methods=['get'])
    def notifications(self, request):
        """Get cached notifications."""
        data = OfflineModeService.get_cached_data(
            user_id=str(request.user.id),
            data_type='notification'
        )
        return Response({'results': data or []})


class SyncQueueViewSet(viewsets.ModelViewSet):
    """
    ViewSet for sync queue management.
    """
    serializer_class = SyncQueueSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get user's sync queue items."""
        return SyncQueue.objects.filter(
            user=self.request.user
        ).order_by('-priority', 'created_at')
    
    @action(
        detail=False,
        methods=['post'],
        serializer_class=QueueActionSerializer
    )
    def queue_action(self, request):
        """Queue an offline action."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        queue_item = OfflineModeService.queue_offline_action(
            user_id=str(request.user.id),
            **serializer.validated_data
        )
        
        return Response(
            SyncQueueSerializer(queue_item).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def process(self, request):
        """Process pending sync queue items."""
        result = OfflineModeService.process_sync_queue(
            str(request.user.id)
        )
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending sync items."""
        pending = self.get_queryset().filter(status='pending')
        page = self.paginate_queryset(pending)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def failed(self, request):
        """Get failed sync items."""
        failed = self.get_queryset().filter(status='failed')
        page = self.paginate_queryset(failed)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(failed, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry a failed sync item."""
        item = self.get_object()
        
        if item.status != 'failed':
            return Response(
                {'error': 'Can only retry failed items'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reset status to pending
        item.status = 'pending'
        item.error_message = ''
        item.save()
        
        return Response({'message': 'Item queued for retry'})


class OfflineLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for offline logs.
    """
    serializer_class = OfflineLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get user's offline logs."""
        queryset = OfflineLog.objects.filter(
            user=self.request.user
        ).order_by('-created_at')
        
        # Filter by log type
        log_type = self.request.query_params.get('log_type')
        if log_type:
            queryset = queryset.filter(log_type=log_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get log summary by type."""
        logs = self.get_queryset()
        
        summary = {}
        for log_type, label in OfflineLog.LOG_TYPES:
            count = logs.filter(log_type=log_type).count()
            summary[log_type] = {
                'label': label,
                'count': count
            }
        
        return Response(summary)
