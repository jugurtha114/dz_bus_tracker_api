from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsAdminOrReadOnly
from .models import Line, Stop, LineStop, LineBus, Favorite
from .serializers import (
    LineSerializer,
    LineDetailSerializer,
    LineCreateSerializer,
    StopSerializer,
    StopListSerializer,
    LineStopSerializer,
    LineStopCreateSerializer,
    LineBusSerializer,
    LineBusCreateSerializer,
    FavoriteSerializer,
    LineStatusSerializer
)
from .selectors import (
    get_line_by_id,
    get_active_lines,
    get_lines_with_active_buses,
    get_line_stops,
    get_favorites_for_user,
    is_line_favorited,
    get_stop_by_id,
    get_nearest_stops,
    get_lines_for_stop,
    get_buses_for_line,
    search_lines,
    search_stops,
    get_connected_lines,
    get_line_status
)
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsAdminOrReadOnly
from .models import Line, Stop, LineStop, LineBus, Favorite
from .serializers import (
    LineSerializer,
    LineDetailSerializer,
    LineCreateSerializer,
    StopSerializer,
    StopListSerializer,
    LineStopSerializer,
    LineStopCreateSerializer,
    LineBusSerializer,
    LineBusCreateSerializer,
    FavoriteSerializer,
    LineStatusSerializer
)
from .selectors import (
    get_line_by_id,
    get_active_lines,
    get_lines_with_active_buses,
    get_line_stops,
    get_favorites_for_user,
    is_line_favorited,
    get_stop_by_id,
    get_nearest_stops,
    get_lines_for_stop,
    get_buses_for_line,
    search_lines,
    search_stops,
    get_connected_lines,
    get_line_status
)
from .services import (
    create_line,
    update_line,
    add_stop_to_line,
    remove_stop_from_line,
    reorder_line_stops,
    create_stop,
    update_stop,
    add_bus_to_line,
    remove_bus_from_line,
    add_favorite,
    remove_favorite,
    update_favorite_threshold,
    calculate_line_path,
    calculate_line_distances
)


class LineViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Line.objects.all()
    serializer_class = LineSerializer
    select_related_fields = ['start_location', 'end_location']
    prefetch_related_fields = ['line_stops', 'line_buses']
    search_fields = ['name', 'description', 'start_location__name', 'end_location__name']
    permission_classes = [IsAdminOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LineDetailSerializer
        elif self.action == 'create':
            return LineCreateSerializer
        elif self.action == 'status':
            return LineStatusSerializer
        return LineSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            active = active.lower() == 'true'
            queryset = queryset.filter(is_active=active)
        
        # Filter by having active buses
        has_active_buses = self.request.query_params.get('has_active_buses')
        if has_active_buses is not None:
            has_active_buses = has_active_buses.lower() == 'true'
            if has_active_buses:
                queryset = queryset.filter(tracking_sessions__status='active', tracking_sessions__is_active=True).distinct()
        
        return queryset
    
    def perform_create(self, serializer):
        create_line(
            data=serializer.validated_data,
            stops_data=getattr(serializer, 'stops_data', [])
        )
    
    def perform_update(self, serializer):
        update_line(
            line_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    @action(detail=True, methods=['get'])
    def stops(self, request, pk=None):
        line = self.get_object()
        line_stops = get_line_stops(line.id)
        
        serializer = LineStopSerializer(line_stops, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_stop(self, request, pk=None):
        line = self.get_object()
        serializer = LineStopCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        line_stop = add_stop_to_line(
            line_id=line.id,
            stop_id=serializer.validated_data['stop'].id,
            order=serializer.validated_data.get('order'),
            distance_from_start=serializer.validated_data.get('distance_from_start', 0),
            estimated_time_from_start=serializer.validated_data.get('estimated_time_from_start', 0)
        )
        
        return Response(LineStopSerializer(line_stop).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def remove_stop(self, request, pk=None):
        line = self.get_object()
        stop_id = request.data.get('stop_id')
        
        if not stop_id:
            return Response(
                {'detail': 'Stop ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success = remove_stop_from_line(line.id, stop_id)
        
        if success:
            return Response({'detail': 'Stop removed from line.'})
        
        return Response(
            {'detail': 'Failed to remove stop from line.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def reorder_stops(self, request, pk=None):
        line = self.get_object()
        stop_orders = request.data.get('stop_orders')
        
        if not stop_orders or not isinstance(stop_orders, dict):
            return Response(
                {'detail': 'Stop orders dictionary is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success = reorder_line_stops(line.id, stop_orders)
        
        if success:
            return Response({'detail': 'Stops reordered successfully.'})
        
        return Response(
            {'detail': 'Failed to reorder stops.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def buses(self, request, pk=None):
        line = self.get_object()
        line_buses = get_buses_for_line(line.id)
        
        serializer = LineBusSerializer(line_buses, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_bus(self, request, pk=None):
        line = self.get_object()
        serializer = LineBusCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        line_bus = add_bus_to_line(
            line_id=line.id,
            bus_id=serializer.validated_data['bus'].id,
            is_primary=serializer.validated_data.get('is_primary', False)
        )
        
        return Response(LineBusSerializer(line_bus).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def remove_bus(self, request, pk=None):
        line = self.get_object()
        bus_id = request.data.get('bus_id')
        
        if not bus_id:
            return Response(
                {'detail': 'Bus ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success = remove_bus_from_line(line.id, bus_id)
        
        if success:
            return Response({'detail': 'Bus removed from line.'})
        
        return Response(
            {'detail': 'Failed to remove bus from line.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def calculate_path(self, request, pk=None):
        line = self.get_object()
        
        path = calculate_line_path(line.id)
        
        return Response({'path': path})
    
    @action(detail=True, methods=['post'])
    def calculate_distances(self, request, pk=None):
        line = self.get_object()
        
        updated_line = calculate_line_distances(line.id)
        
        return Response(LineSerializer(updated_line).data)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        line = self.get_object()
        
        status_data = get_line_status(line.id)
        
        if not status_data:
            return Response(
                {'detail': 'Line status not available.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(data=status_data)
        serializer.is_valid()  # Already formatted correctly, no need to raise_exception
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        lines = get_active_lines()
        
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def with_active_buses(self, request):
        lines = get_lines_with_active_buses()
        
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q')
        
        if not query:
            return Response(
                {'detail': 'Search query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lines = search_lines(query)
        
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_stop(self, request):
        stop_id = request.query_params.get('stop_id')
        
        if not stop_id:
            return Response(
                {'detail': 'Stop ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lines = get_lines_for_stop(stop_id)
        
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def connecting(self, request):
        start_stop_id = request.query_params.get('start_stop_id')
        end_stop_id = request.query_params.get('end_stop_id')
        
        if not start_stop_id or not end_stop_id:
            return Response(
                {'detail': 'Start and end stop IDs are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lines = get_connected_lines(start_stop_id, end_stop_id)
        
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def favorite(self, request, pk=None):
        line = self.get_object()
        
        notification_threshold = request.data.get('notification_threshold', 5)
        
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        favorite = add_favorite(
            user=request.user,
            line_id=line.id,
            notification_threshold=notification_threshold
        )
        
        return Response(FavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def unfavorite(self, request, pk=None):
        line = self.get_object()
        
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        success = remove_favorite(
            user=request.user,
            line_id=line.id
        )
        
        if success:
            return Response({'detail': 'Line removed from favorites.'})
        
        return Response(
            {'detail': 'Failed to remove line from favorites.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def is_favorite(self, request, pk=None):
        line = self.get_object()
        
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        is_favorite = is_line_favorited(request.user, line.id)
        
        return Response({'is_favorite': is_favorite})


class StopViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Stop.objects.all()
    serializer_class = StopSerializer
    parser_classes = [MultiPartParser, FormParser]
    search_fields = ['name', 'code', 'address']
    permission_classes = [IsAdminOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return StopListSerializer
        return StopSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            active = active.lower() == 'true'
            queryset = queryset.filter(is_active=active)
        
        return queryset
    
    def perform_create(self, serializer):
        create_stop(serializer.validated_data)
    
    def perform_update(self, serializer):
        update_stop(
            stop_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q')
        
        if not query:
            return Response(
                {'detail': 'Search query is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        stops = search_stops(query)
        
        page = self.paginate_queryset(stops)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(stops, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def nearest(self, request):
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        radius = request.query_params.get('radius', 1000)
        limit = request.query_params.get('limit', 5)
        
        if not latitude or not longitude:
            return Response(
                {'detail': 'Latitude and longitude are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            radius = int(radius)
            limit = int(limit)
        except ValueError:
            return Response(
                {'detail': 'Radius and limit must be integers.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        stops = get_nearest_stops(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            limit=limit
        )
        
        serializer = self.get_serializer(stops, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        stop = self.get_object()
        lines = get_lines_for_stop(stop.id)
        
        serializer = LineSerializer(lines, many=True)
        return Response(serializer.data)


class LineStopViewSet(BaseViewSet):
    queryset = LineStop.objects.all()
    serializer_class = LineStopSerializer
    permission_classes = [IsAdminOrReadOnly]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by stop
        stop_id = self.request.query_params.get('stop')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)
        
        return queryset.select_related('line', 'stop')


class LineBusViewSet(BaseViewSet):
    queryset = LineBus.objects.all()
    serializer_class = LineBusSerializer
    permission_classes = [IsAdminOrReadOnly]
    
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
        
        return queryset.select_related('line', 'bus', 'bus__driver')


class FavoriteViewSet(BaseViewSet):
    queryset = Favorite.objects.all()
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only show favorites for the current user
        return self.queryset.filter(
            user=self.request.user
        ).select_related('line', 'line__start_location', 'line__end_location')
    
    def perform_create(self, serializer):
        add_favorite(
            user=self.request.user,
            line_id=serializer.validated_data['line'].id,
            notification_threshold=serializer.validated_data.get('notification_threshold', 5)
        )
    
    @action(detail=True, methods=['post'])
    def update_threshold(self, request, pk=None):
        favorite = self.get_object()
        notification_threshold = request.data.get('notification_threshold')
        
        if notification_threshold is None:
            return Response(
                {'detail': 'Notification threshold is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            notification_threshold = int(notification_threshold)
        except ValueError:
            return Response(
                {'detail': 'Notification threshold must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_favorite = update_favorite_threshold(
            user=self.request.user,
            line_id=favorite.line.id,
            notification_threshold=notification_threshold
        )
        
        return Response(FavoriteSerializer(updated_favorite).data)