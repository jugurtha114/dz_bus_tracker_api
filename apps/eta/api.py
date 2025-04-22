from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsAdminOrReadOnly, IsDriver
from .models import ETA, ETANotification, StopArrival
from .serializers import (
    ETASerializer,
    ETACreateSerializer,
    ETAUpdateSerializer,
    ETANotificationSerializer,
    ETANotificationCreateSerializer,
    StopArrivalSerializer,
    StopArrivalCreateSerializer,
    NextArrivalSerializer
)
from .selectors import (
    get_eta_by_id,
    get_eta_for_bus_stop,
    get_etas_for_stop,
    get_etas_for_line,
    get_etas_for_bus,
    get_eta_notifications_for_user,
    get_arrivals_for_stop,
    get_arrivals_for_bus,
    get_arrivals_for_line,
    get_delayed_etas
)
from .services import (
    calculate_eta,
    recalculate_etas_for_line,
    record_stop_arrival,
    update_stop_departure,
    create_eta_notification,
    send_eta_notifications,
    get_next_arrivals
)


class ETAViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = ETA.objects.all()
    serializer_class = ETASerializer
    select_related_fields = ['line', 'bus', 'stop', 'tracking_session']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ETACreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ETAUpdateSerializer
        return ETASerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by stop
        stop_id = self.request.query_params.get('stop')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by time range
        min_time = self.request.query_params.get('min_time')
        if min_time:
            queryset = queryset.filter(estimated_arrival_time__gte=min_time)
        
        max_time = self.request.query_params.get('max_time')
        if max_time:
            queryset = queryset.filter(estimated_arrival_time__lte=max_time)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def calculate(self, request):
        tracking_session_id = request.data.get('tracking_session_id')
        stop_id = request.data.get('stop_id')
        
        if not tracking_session_id or not stop_id:
            return Response(
                {'detail': 'Tracking session ID and stop ID are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            eta = calculate_eta(tracking_session_id, stop_id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not eta:
            return Response(
                {'detail': 'Could not calculate ETA.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(ETASerializer(eta).data)
    
    @action(detail=False, methods=['post'])
    def recalculate_line(self, request):
        line_id = request.data.get('line_id')
        
        if not line_id:
            return Response(
                {'detail': 'Line ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            updated_etas = recalculate_etas_for_line(line_id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'detail': 'ETAs recalculated successfully.',
            'count': len(updated_etas)
        })
    
    @action(detail=False, methods=['get'])
    def for_stop(self, request):
        stop_id = request.query_params.get('stop_id')
        limit = request.query_params.get('limit', 10)
        
        if not stop_id:
            return Response(
                {'detail': 'Stop ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 10
        
        etas = get_etas_for_stop(stop_id, limit=limit)
        
        serializer = self.get_serializer(etas, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_line(self, request):
        line_id = request.query_params.get('line_id')
        limit = request.query_params.get('limit', 20)
        
        if not line_id:
            return Response(
                {'detail': 'Line ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        
        etas = get_etas_for_line(line_id, limit=limit)
        
        serializer = self.get_serializer(etas, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_bus(self, request):
        bus_id = request.query_params.get('bus_id')
        limit = request.query_params.get('limit', 20)
        
        if not bus_id:
            return Response(
                {'detail': 'Bus ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        
        etas = get_etas_for_bus(bus_id, limit=limit)
        
        serializer = self.get_serializer(etas, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def next_arrivals(self, request):
        stop_id = request.query_params.get('stop_id')
        limit = request.query_params.get('limit', 5)
        
        if not stop_id:
            return Response(
                {'detail': 'Stop ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 5
        
        try:
            arrivals = get_next_arrivals(stop_id, limit=limit)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = NextArrivalSerializer(arrivals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def delayed(self, request):
        delay_threshold = request.query_params.get('threshold', 5)
        limit = request.query_params.get('limit', 20)
        
        try:
            delay_threshold = int(delay_threshold)
            limit = int(limit)
        except ValueError:
            delay_threshold = 5
            limit = 20
        
        etas = get_delayed_etas(delay_threshold=delay_threshold, limit=limit)
        
        serializer = self.get_serializer(etas, many=True)
        return Response(serializer.data)


class ETANotificationViewSet(BaseViewSet):
    queryset = ETANotification.objects.all()
    serializer_class = ETANotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ETANotificationCreateSerializer
        return ETANotificationSerializer
    
    def get_queryset(self):
        # Only show notifications for the current user
        return self.queryset.filter(
            user=self.request.user
        ).select_related('eta', 'eta__line', 'eta__bus', 'eta__stop')
    
    def perform_create(self, serializer):
        create_eta_notification(
            eta_id=serializer.validated_data['eta'].id,
            user_id=self.request.user.id,
            threshold=serializer.validated_data.get('notification_threshold', 5),
            notification_type=serializer.validated_data.get('notification_type', 'push')
        )
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        notifications = get_eta_notifications_for_user(
            user_id=request.user.id,
            sent=False
        )
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sent(self, request):
        notifications = get_eta_notifications_for_user(
            user_id=request.user.id,
            sent=True
        )
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def send_pending(self, request):
        if not request.user.is_admin:
            return Response(
                {'detail': 'Only admins can trigger sending notifications.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        sent_count = send_eta_notifications()
        
        return Response({
            'detail': 'Notifications sent successfully.',
            'count': sent_count
        })


class StopArrivalViewSet(BaseViewSet):
    queryset = StopArrival.objects.all()
    serializer_class = StopArrivalSerializer
    select_related_fields = ['tracking_session', 'line', 'stop', 'bus']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StopArrivalCreateSerializer
        return StopArrivalSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsDriver()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by tracking session
        session_id = self.request.query_params.get('session')
        if session_id:
            queryset = queryset.filter(tracking_session_id=session_id)
        
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by stop
        stop_id = self.request.query_params.get('stop')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by time range
        start_time = self.request.query_params.get('start_time')
        if start_time:
            queryset = queryset.filter(arrival_time__gte=start_time)
        
        end_time = self.request.query_params.get('end_time')
        if end_time:
            queryset = queryset.filter(arrival_time__lte=end_time)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def record_arrival(self, request):
        tracking_session_id = request.data.get('tracking_session_id')
        stop_id = request.data.get('stop_id')
        
        if not tracking_session_id or not stop_id:
            return Response(
                {'detail': 'Tracking session ID and stop ID are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            arrival = record_stop_arrival(tracking_session_id, stop_id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(StopArrivalSerializer(arrival).data)
    
    @action(detail=True, methods=['post'])
    def record_departure(self, request, pk=None):
        arrival = self.get_object()
        
        try:
            updated_arrival = update_stop_departure(arrival.id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(StopArrivalSerializer(updated_arrival).data)
    
    @action(detail=False, methods=['get'])
    def for_stop(self, request):
        stop_id = request.query_params.get('stop_id')
        limit = request.query_params.get('limit', 20)
        start_time = request.query_params.get('start_time')
        end_time = request.query_params.get('end_time')
        
        if not stop_id:
            return Response(
                {'detail': 'Stop ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        
        arrivals = get_arrivals_for_stop(
            stop_id=stop_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        serializer = self.get_serializer(arrivals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_bus(self, request):
        bus_id = request.query_params.get('bus_id')
        limit = request.query_params.get('limit', 20)
        start_time = request.query_params.get('start_time')
        end_time = request.query_params.get('end_time')
        
        if not bus_id:
            return Response(
                {'detail': 'Bus ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        
        arrivals = get_arrivals_for_bus(
            bus_id=bus_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        serializer = self.get_serializer(arrivals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_line(self, request):
        line_id = request.query_params.get('line_id')
        limit = request.query_params.get('limit', 20)
        start_time = request.query_params.get('start_time')
        end_time = request.query_params.get('end_time')
        
        if not line_id:
            return Response(
                {'detail': 'Line ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = int(limit)
        except ValueError:
            limit = 20
        
        arrivals = get_arrivals_for_line(
            line_id=line_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        serializer = self.get_serializer(arrivals, many=True)
        return Response(serializer.data)