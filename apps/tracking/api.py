from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.base.api import BaseViewSet, BaseAPIView
from apps.core.base.permissions import (
    IsDriver, IsAdmin, IsAdminOrReadOnly, IsDriverWithVerifiedBus
)
from .models import TrackingSession, LocationUpdate, TrackingLog, OfflineLocationBatch
from .serializers import (
    TrackingSessionSerializer,
    TrackingSessionCreateSerializer,
    LocationUpdateSerializer,
    LocationUpdateCreateSerializer,
    BatchLocationUpdateSerializer,
    OfflineLocationBatchSerializer,
    OfflineLocationBatchCreateSerializer,
    TrackingLogSerializer,
    CurrentLocationSerializer,
)
from .selectors import (
    get_active_tracking_sessions,
    get_tracking_session_by_id,
    get_location_updates_for_session,
    get_tracking_logs_for_session,
    get_latest_location_for_session,
    get_active_sessions_for_line,
    get_active_sessions_for_bus,
    get_active_sessions_for_driver,
)
from .services import (
    start_tracking_session,
    end_tracking_session,
    pause_tracking_session,
    resume_tracking_session,
    add_location_update,
    batch_location_updates,
    create_offline_batch,
    process_offline_batch,
    log_tracking_event,
    get_current_location,
)


class TrackingSessionViewSet(BaseViewSet):
    """
    API endpoint for tracking sessions.
    """
    queryset = TrackingSession.objects.all()
    serializer_class = TrackingSessionSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'start_tracking', 'end_tracking', 'pause_tracking', 'resume_tracking']:
            return [permissions.IsAuthenticated(), IsDriverWithVerifiedBus()]
        elif self.action in ['destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action in ['create', 'start_tracking']:
            return TrackingSessionCreateSerializer
        return TrackingSessionSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by driver
        driver_param = self.request.query_params.get('driver')
        if driver_param:
            queryset = queryset.filter(driver__id=driver_param)
        
        # Filter by bus
        bus_param = self.request.query_params.get('bus')
        if bus_param:
            queryset = queryset.filter(bus__id=bus_param)
        
        # Filter by line
        line_param = self.request.query_params.get('line')
        if line_param:
            queryset = queryset.filter(line__id=line_param)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def start_tracking(self, request):
        """
        Start a new tracking session.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        session = start_tracking_session(
            driver=serializer.validated_data['driver'],
            bus=serializer.validated_data['bus'],
            line=serializer.validated_data['line'],
            schedule=serializer.validated_data.get('schedule'),
        )
        
        if not session:
            return Response(
                {'detail': 'Failed to start tracking session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            TrackingSessionSerializer(session).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def end_tracking(self, request, pk=None):
        """
        End a tracking session.
        """
        session = self.get_object()
        
        # Check if the session belongs to the driver
        if request.user.is_driver and session.driver.user.id != request.user.id:
            return Response(
                {'detail': 'You can only end your own tracking sessions.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        updated_session = end_tracking_session(session.id)
        
        if not updated_session:
            return Response(
                {'detail': 'Failed to end tracking session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(TrackingSessionSerializer(updated_session).data)
    
    @action(detail=True, methods=['post'])
    def pause_tracking(self, request, pk=None):
        """
        Pause a tracking session.
        """
        session = self.get_object()
        
        # Check if the session belongs to the driver
        if request.user.is_driver and session.driver.user.id != request.user.id:
            return Response(
                {'detail': 'You can only pause your own tracking sessions.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        updated_session = pause_tracking_session(session.id)
        
        if not updated_session:
            return Response(
                {'detail': 'Failed to pause tracking session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(TrackingSessionSerializer(updated_session).data)
    
    @action(detail=True, methods=['post'])
    def resume_tracking(self, request, pk=None):
        """
        Resume a tracking session.
        """
        session = self.get_object()
        
        # Check if the session belongs to the driver
        if request.user.is_driver and session.driver.user.id != request.user.id:
            return Response(
                {'detail': 'You can only resume your own tracking sessions.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        updated_session = resume_tracking_session(session.id)
        
        if not updated_session:
            return Response(
                {'detail': 'Failed to resume tracking session.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(TrackingSessionSerializer(updated_session).data)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        Get all active tracking sessions.
        """
        sessions = get_active_tracking_sessions()
        
        # Filter by line
        line_param = request.query_params.get('line')
        if line_param:
            sessions = get_active_sessions_for_line(line_param)
        
        # Filter by bus
        bus_param = request.query_params.get('bus')
        if bus_param:
            sessions = get_active_sessions_for_bus(bus_param)
        
        # Filter by driver
        driver_param = request.query_params.get('driver')
        if driver_param:
            sessions = get_active_sessions_for_driver(driver_param)
        
        page = self.paginate_queryset(sessions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def location_updates(self, request, pk=None):
        """
        Get location updates for a tracking session.
        """
        session = self.get_object()
        
        # Optional start and end datetime params
        start_time = request.query_params.get('start_time')
        end_time = request.query_params.get('end_time')
        
        location_updates = get_location_updates_for_session(
            session.id,
            start_time=start_time,
            end_time=end_time
        )
        
        page = self.paginate_queryset(location_updates)
        if page is not None:
            serializer = LocationUpdateSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = LocationUpdateSerializer(location_updates, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """
        Get logs for a tracking session.
        """
        session = self.get_object()
        logs = get_tracking_logs_for_session(session.id)
        
        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = TrackingLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = TrackingLogSerializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def current_location(self, request, pk=None):
        """
        Get the current location of a tracking session.
        """
        session = self.get_object()
        location = get_current_location(session.id)
        
        if not location:
            return Response(
                {'detail': 'No location data available.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(location)


class LocationUpdateViewSet(BaseViewSet):
    """
    API endpoint for location updates.
    """
    queryset = LocationUpdate.objects.all()
    serializer_class = LocationUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create']:
            return LocationUpdateCreateSerializer
        return LocationUpdateSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated(), IsDriverWithVerifiedBus()]
        elif self.action in ['destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by session
        session_param = self.request.query_params.get('session')
        if session_param:
            queryset = queryset.filter(session__id=session_param)
        
        # Filter by time range
        start_time = self.request.query_params.get('start_time')
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        
        end_time = self.request.query_params.get('end_time')
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)
        
        return queryset
    
    def perform_create(self, serializer):
        add_location_update(
            serializer.validated_data['session'].id,
            serializer.validated_data
        )


class BatchLocationUpdateAPIView(BaseAPIView):
    """
    API endpoint for batch location updates.
    """
    permission_classes = [permissions.IsAuthenticated, IsDriverWithVerifiedBus]
    serializer_class = BatchLocationUpdateSerializer
    
    def post(self, request):
        """
        Process a batch of location updates.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        session_id = serializer.validated_data['session_id']
        locations = serializer.validated_data['locations']
        
        created_updates = batch_location_updates(session_id, locations)
        
        if not created_updates:
            return Response(
                {'detail': 'Failed to process batch updates.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'detail': f'Processed {len(created_updates)} location updates.',
            'count': len(created_updates)
        })


class OfflineLocationBatchViewSet(BaseViewSet):
    """
    API endpoint for offline location batches.
    """
    queryset = OfflineLocationBatch.objects.all()
    serializer_class = OfflineLocationBatchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create']:
            return OfflineLocationBatchCreateSerializer
        return OfflineLocationBatchSerializer
    
    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated(), IsDriverWithVerifiedBus()]
        elif self.action in ['destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by driver
        driver_param = self.request.query_params.get('driver')
        if driver_param:
            queryset = queryset.filter(driver__id=driver_param)
        
        # Filter by bus
        bus_param = self.request.query_params.get('bus')
        if bus_param:
            queryset = queryset.filter(bus__id=bus_param)
        
        # Filter by line
        line_param = self.request.query_params.get('line')
        if line_param:
            queryset = queryset.filter(line__id=line_param)
        
        # Filter by processed status
        processed_param = self.request.query_params.get('processed')
        if processed_param is not None:
            processed = processed_param.lower() == 'true'
            queryset = queryset.filter(processed=processed)
        
        return queryset
    
    def perform_create(self, serializer):
        create_offline_batch(
            driver=serializer.validated_data['driver'],
            bus=serializer.validated_data['bus'],
            line=serializer.validated_data['line'],
            location_data=serializer.validated_data['data']
        )
    
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """
        Process an offline batch.
        """
        batch = self.get_object()
        
        if batch.processed:
            return Response({'detail': 'Batch already processed.'})
        
        success = process_offline_batch(batch)
        
        if not success:
            return Response(
                {'detail': 'Failed to process batch.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({'detail': 'Batch processed successfully.'})


class TrackingLogViewSet(BaseViewSet):
    """
    API endpoint for tracking logs.
    """
    queryset = TrackingLog.objects.all()
    serializer_class = TrackingLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        else:
            return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by session
        session_param = self.request.query_params.get('session')
        if session_param:
            queryset = queryset.filter(session__id=session_param)
        
        # Filter by event type
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        # Filter by time range
        start_time = self.request.query_params.get('start_time')
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        
        end_time = self.request.query_params.get('end_time')
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)
        
        return queryset