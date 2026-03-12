"""
Views for the lines API.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet
from apps.core.permissions import IsAdmin, IsAdminOrReadOnly
from apps.lines.models import Line, LineStop, Schedule, ServiceDisruption, Stop
from apps.lines.services import LineService, ScheduleService, StopService

from .filters import LineFilter, ScheduleFilter, StopFilter
from .serializers import (
    AddStopToLineSerializer,
    LineCreateSerializer,
    LineSerializer,
    LineStopSerializer,
    LineUpdateSerializer,
    RemoveStopFromLineSerializer,
    ScheduleCreateSerializer,
    ScheduleSerializer,
    ServiceDisruptionCreateSerializer,
    ServiceDisruptionSerializer,
    StopCreateSerializer,
    StopSerializer,
    StopUpdateSerializer,
    UpdateStopOrderSerializer,
)


class StopViewSet(BaseModelViewSet):
    """
    API endpoint for stops.
    """
    queryset = Stop.objects.all()
    serializer_class = StopSerializer
    filterset_class = StopFilter
    service_class = StopService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminOrReadOnly()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return StopCreateSerializer
        if self.action in ['update', 'partial_update']:
            return StopUpdateSerializer
        return StopSerializer

    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        """
        Get lines that pass through this stop.
        """
        stop = self.get_object()

        # Get lines for this stop
        lines = stop.lines.filter(is_active=True)

        # Apply pagination
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = LineSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = LineSerializer(lines, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def nearby(self, request):
        """
        Get stops near a location.
        """
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        radius = request.query_params.get('radius', 0.5)  # Default 500m

        if not latitude or not longitude:
            return Response(
                {'detail': 'Latitude and longitude are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get nearby stops
        from apps.lines.selectors import get_nearby_stops
        stops = get_nearby_stops(
            latitude=float(latitude),
            longitude=float(longitude),
            radius_km=float(radius)
        )

        # Sort by distance
        sorted_stops = sorted(stops, key=lambda x: getattr(x, 'distance', float('inf')))

        # Apply pagination
        page = self.paginate_queryset(sorted_stops)
        if page is not None:
            response_data = []
            for stop in page:
                stop_data = StopSerializer(stop, context={'request': request}).data
                stop_data['distance'] = getattr(stop, 'distance', None)
                response_data.append(stop_data)
            return self.get_paginated_response(response_data)

        # Fallback (no pagination configured)
        response_data = []
        for stop in sorted_stops:
            stop_data = StopSerializer(stop, context={'request': request}).data
            stop_data['distance'] = getattr(stop, 'distance', None)
            response_data.append(stop_data)
        return Response(response_data)


class LineViewSet(BaseModelViewSet):
    """
    API endpoint for lines.
    """
    queryset = Line.objects.all()
    serializer_class = LineSerializer
    filterset_class = LineFilter
    service_class = LineService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve', 'stops', 'schedules', 'journey']:
            return [IsAuthenticated()]
        return [IsAdminOrReadOnly()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return LineCreateSerializer
        if self.action in ['update', 'partial_update']:
            return LineUpdateSerializer
        if self.action == 'add_stop':
            return AddStopToLineSerializer
        if self.action == 'remove_stop':
            return RemoveStopFromLineSerializer
        if self.action == 'update_stop_order':
            return UpdateStopOrderSerializer
        if self.action == 'add_schedule':
            return ScheduleCreateSerializer
        return LineSerializer

    @action(detail=True, methods=['get'])
    def stops(self, request, pk=None):
        """
        Get stops for this line.
        """
        line = self.get_object()

        # Get stops in order
        line_stops = line.line_stops.all().order_by('order')

        # Apply pagination
        page = self.paginate_queryset(line_stops)
        if page is not None:
            serializer = LineStopSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = LineStopSerializer(line_stops, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_stop(self, request, pk=None):
        """
        Add a stop to this line.
        """
        line = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Add stop to line
        line_stop = LineService.add_stop_to_line(
            line_id=line.id,
            stop_id=serializer.validated_data['stop_id'],
            order=serializer.validated_data['order'],
            distance_from_previous=serializer.validated_data.get('distance_from_previous'),
            average_time_from_previous=serializer.validated_data.get('average_time_from_previous')
        )

        response_serializer = LineStopSerializer(line_stop)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def remove_stop(self, request, pk=None):
        """
        Remove a stop from this line.
        """
        line = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Remove stop from line
        LineService.remove_stop_from_line(
            line_id=line.id,
            stop_id=serializer.validated_data['stop_id']
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def update_stop_order(self, request, pk=None):
        """
        Update a stop's order in this line.
        """
        line = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Update stop order
        line_stop = LineService.update_line_stop_order(
            line_id=line.id,
            stop_id=serializer.validated_data['stop_id'],
            new_order=serializer.validated_data['new_order']
        )

        response_serializer = LineStopSerializer(line_stop)
        return Response(response_serializer.data)

    @action(detail=True, methods=['get'])
    def schedules(self, request, pk=None):
        """
        Get schedules for this line.
        """
        line = self.get_object()

        # Filter by day of week if provided
        day_of_week = request.query_params.get('day_of_week')
        schedules = line.schedules.all()

        if day_of_week is not None and day_of_week.isdigit():
            schedules = schedules.filter(day_of_week=int(day_of_week))

        schedules = schedules.order_by('day_of_week', 'start_time')

        # Apply pagination
        page = self.paginate_queryset(schedules)
        if page is not None:
            serializer = ScheduleSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_schedule(self, request, pk=None):
        """
        Add a schedule to this line.
        """
        line = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create schedule
        schedule = ScheduleService.create_schedule(
            line_id=line.id,
            **serializer.validated_data
        )

        response_serializer = ScheduleSerializer(schedule)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate a line.
        """
        line = self.get_object()

        # Activate line
        LineService.update_line(line.id, is_active=True)

        return Response({'detail': 'Line activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate a line.
        """
        line = self.get_object()

        # Deactivate line
        LineService.update_line(line.id, is_active=False)

        return Response({'detail': 'Line deactivated'})

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Search for lines.
        """
        query = request.query_params.get('q', '')
        if not query:
            return Response(
                {'detail': 'Search query is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Search for lines
        from apps.lines.selectors import search_lines
        lines = search_lines(query)

        # Apply pagination
        page = self.paginate_queryset(lines)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(lines, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def journey(self, request):
        """
        Find route options between two stops.

        Query params:
          - from_stop (UUID): departure stop ID
          - to_stop (UUID): destination stop ID
        """
        from_stop_id = request.query_params.get('from_stop')
        to_stop_id = request.query_params.get('to_stop')

        if not from_stop_id or not to_stop_id:
            return Response(
                {'detail': 'Both from_stop and to_stop parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.lines.services import JourneyService
        routes = JourneyService.find_routes(from_stop_id, to_stop_id)

        return Response({
            'from_stop': from_stop_id,
            'to_stop': to_stop_id,
            'routes': routes,
        })


class ScheduleViewSet(BaseModelViewSet):
    """
    API endpoint for schedules.
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    filterset_class = ScheduleFilter

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        """
        Filter schedules based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        # Filter by day of week if provided
        day_of_week = self.request.query_params.get('day_of_week')
        if day_of_week is not None and day_of_week.isdigit():
            queryset = queryset.filter(day_of_week=int(day_of_week))

        # Order by day of week and start time
        return queryset.order_by('day_of_week', 'start_time')


class ServiceDisruptionViewSet(BaseModelViewSet):
    """
    API endpoint for service disruptions on bus lines.

    Admins can create disruptions; all authenticated users can read them.
    Creating a disruption automatically broadcasts a Celery notification to admins.
    """
    queryset = ServiceDisruption.objects.select_related('line', 'created_by').all()
    serializer_class = ServiceDisruptionSerializer
    filterset_fields = ['line', 'is_active', 'disruption_type']

    def get_permissions(self):
        """
        Read access for all authenticated users; write access for admins only.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ServiceDisruptionCreateSerializer
        return ServiceDisruptionSerializer

    def perform_create(self, serializer):
        """
        Save disruption with the requesting user as creator, then broadcast.
        """
        import logging
        disruption = serializer.save(created_by=self.request.user)
        try:
            from apps.lines.tasks import broadcast_disruption
            broadcast_disruption.delay(str(disruption.id))
        except Exception:
            logging.getLogger(__name__).warning(
                f"broadcast_disruption task could not be queued for {disruption.id}"
            )
