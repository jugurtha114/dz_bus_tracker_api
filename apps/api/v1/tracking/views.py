"""
Views for the tracking API.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet, ReadOnlyModelViewSet
from apps.core.permissions import IsAdmin, IsApprovedDriver, IsDriverOrAdmin
from apps.tracking.models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)
from apps.tracking.services import (
    AnomalyService,
    BusLineService,
    LocationUpdateService,
    PassengerCountService,
    TripService,
)

from .filters import (
    AnomalyFilter,
    BusLineFilter,
    LocationUpdateFilter,
    PassengerCountFilter,
    TripFilter,
    WaitingPassengersFilter,
)
from .serializers import (
    AnomalyCreateSerializer,
    AnomalyResolveSerializer,
    AnomalySerializer,
    BusLineCreateSerializer,
    BusLineSerializer,
    EstimateArrivalTimeSerializer,
    LocationUpdateCreateSerializer,
    LocationUpdateSerializer,
    PassengerCountCreateSerializer,
    PassengerCountSerializer,
    StartTrackingSerializer,
    StopTrackingSerializer,
    TripCreateSerializer,
    TripSerializer,
    TripUpdateSerializer,
    WaitingPassengersCreateSerializer,
    WaitingPassengersSerializer,
)


class BusLineViewSet(BaseModelViewSet):
    """
    API endpoint for bus-line assignments.
    """
    queryset = BusLine.objects.all()
    serializer_class = BusLineSerializer
    filterset_class = BusLineFilter
    service_class = BusLineService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        if self.action in ['start_tracking', 'stop_tracking']:
            return [IsApprovedDriver()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return BusLineCreateSerializer
        if self.action == 'start_tracking':
            return StartTrackingSerializer
        if self.action == 'stop_tracking':
            return StopTrackingSerializer
        return BusLineSerializer

    def get_queryset(self):
        """
        Filter bus-line assignments based on user type and parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        # Filter by tracking status if provided
        tracking_status = self.request.query_params.get('tracking_status')
        if tracking_status:
            queryset = queryset.filter(tracking_status=tracking_status)

        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        return queryset.select_related('bus', 'line')

    @action(detail=False, methods=['post'])
    def start_tracking(self, request):
        """
        Start tracking a bus on a line.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            return Response(
                {'detail': 'No buses found for this driver'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Start tracking
        bus_line, trip = BusLineService.start_tracking(
            bus_id=bus.id,
            line_id=serializer.validated_data['line_id']
        )

        response_serializer = BusLineSerializer(bus_line)
        return Response(response_serializer.data)

    @action(detail=False, methods=['post'])
    def stop_tracking(self, request):
        """
        Stop tracking a bus on a line.
        """
        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            return Response(
                {'detail': 'No buses found for this driver'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Get active bus-line
        try:
            bus_line = BusLine.objects.get(
                bus=bus,
                is_active=True,
                tracking_status='active'
            )
        except BusLine.DoesNotExist:
            return Response(
                {'detail': 'No active tracking found for this bus'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Stop tracking
        bus_line, trip = BusLineService.stop_tracking(
            bus_id=bus.id,
            line_id=bus_line.line_id
        )

        response_serializer = BusLineSerializer(bus_line)
        return Response(response_serializer.data)


class LocationUpdateViewSet(BaseModelViewSet):
    """
    API endpoint for location updates.
    """
    queryset = LocationUpdate.objects.all()
    serializer_class = LocationUpdateSerializer
    filterset_class = LocationUpdateFilter
    service_class = LocationUpdateService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create']:
            return [IsApprovedDriver()]
        return [IsDriverOrAdmin()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return LocationUpdateCreateSerializer
        if self.action == 'estimate_arrival':
            return EstimateArrivalTimeSerializer
        return LocationUpdateSerializer

    def get_queryset(self):
        """
        Filter location updates based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        # Filter by trip if provided
        trip_id = self.request.query_params.get('trip_id')
        if trip_id:
            queryset = queryset.filter(trip_id=trip_id)

        # Limit to recent updates if requested
        limit = self.request.query_params.get('limit')
        if limit and limit.isdigit():
            queryset = queryset.order_by('-created_at')[:int(limit)]
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def perform_create(self, serializer):
        """
        Create a location update for the driver's bus.
        """
        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(self.request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            return Response(
                {'detail': 'No buses found for this driver'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Get active bus-line and trip
        try:
            bus_line = BusLine.objects.get(
                bus=bus,
                is_active=True,
                tracking_status='active'
            )

            trip_id = bus_line.trip_id
            line_id = bus_line.line_id
        except BusLine.DoesNotExist:
            trip_id = None
            line_id = None

        # Create location update
        LocationUpdateService.record_location_update(
            bus_id=bus.id,
            trip_id=trip_id,
            line_id=line_id,
            **serializer.validated_data
        )

    @action(detail=False, methods=['post'])
    def estimate_arrival(self, request):
        """
        Estimate arrival time to a stop.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            return Response(
                {'detail': 'No buses found for this driver'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Get latest location
        try:
            location = LocationUpdate.objects.filter(bus=bus).latest('created_at')
        except LocationUpdate.DoesNotExist:
            return Response(
                {'detail': 'No location data available for this bus'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Estimate arrival time
        from apps.tracking.selectors import estimate_arrival_time
        eta = estimate_arrival_time(
            bus_id=bus.id,
            stop_id=serializer.validated_data['stop_id']
        )

        if not eta:
            return Response(
                {'detail': 'Could not estimate arrival time'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({'eta': eta.isoformat()})


class PassengerCountViewSet(BaseModelViewSet):
    """
    API endpoint for passenger counts.
    """
    queryset = PassengerCount.objects.all()
    serializer_class = PassengerCountSerializer
    filterset_class = PassengerCountFilter
    service_class = PassengerCountService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create']:
            return [IsApprovedDriver()]
        return [IsDriverOrAdmin()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return PassengerCountCreateSerializer
        return PassengerCountSerializer

    def get_queryset(self):
        """
        Filter passenger counts based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        # Filter by trip if provided
        trip_id = self.request.query_params.get('trip_id')
        if trip_id:
            queryset = queryset.filter(trip_id=trip_id)

        # Filter by stop if provided
        stop_id = self.request.query_params.get('stop_id')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """
        Create a passenger count for the driver's bus.
        """
        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(self.request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            return Response(
                {'detail': 'No buses found for this driver'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Get active bus-line and trip
        try:
            bus_line = BusLine.objects.get(
                bus=bus,
                is_active=True,
                tracking_status='active'
            )

            trip_id = bus_line.trip_id
            line_id = bus_line.line_id
        except BusLine.DoesNotExist:
            trip_id = None
            line_id = None

        # Create passenger count
        PassengerCountService.update_passenger_count(
            bus_id=bus.id,
            trip_id=trip_id,
            line_id=line_id,
            **serializer.validated_data
        )

class WaitingPassengersViewSet(BaseModelViewSet):
    """
    API endpoint for waiting passengers.
    """
    queryset = WaitingPassengers.objects.all()
    serializer_class = WaitingPassengersSerializer
    filterset_class = WaitingPassengersFilter
    service_class = PassengerCountService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action == 'create':
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return WaitingPassengersCreateSerializer
        return WaitingPassengersSerializer

    def get_queryset(self):
        """
        Filter waiting passengers based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by stop if provided
        stop_id = self.request.query_params.get('stop_id')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """
        Create a waiting passengers report.
        """
        PassengerCountService.update_waiting_passengers(
            stop_id=serializer.validated_data['stop'],
            count=serializer.validated_data['count'],
            line_id=serializer.validated_data.get('line'),
            user_id=self.request.user.id
        )

class TripViewSet(BaseModelViewSet):
    """
    API endpoint for trips.
    """
    queryset = Trip.objects.all()
    serializer_class = TripSerializer
    filterset_class = TripFilter
    service_class = TripService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve', 'statistics']:
            return [IsAuthenticated()]
        if self.action in ['create']:
            return [IsApprovedDriver()]
        if self.action in ['update', 'partial_update']:
            return [IsDriverOrAdmin()]
        if self.action in ['destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return TripCreateSerializer
        if self.action in ['update', 'partial_update']:
            return TripUpdateSerializer
        return TripSerializer

    def get_queryset(self):
        """
        Filter trips based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Filter by driver if provided
        driver_id = self.request.query_params.get('driver_id')
        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)

        # Filter by line if provided
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)

        # Filter by completion status if provided
        is_completed = self.request.query_params.get('is_completed')
        if is_completed is not None:
            queryset = queryset.filter(is_completed=is_completed == 'true')

        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(start_time__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_time__lte=end_date)

        return queryset.select_related('bus', 'driver', 'line', 'start_stop', 'end_stop')

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """
        Get statistics for a trip.
        """
        trip = self.get_object()

        # Get statistics
        from apps.tracking.selectors import get_trip_statistics
        stats = get_trip_statistics(trip.id)

        return Response(stats)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        """
        End a trip.
        """
        trip = self.get_object()

        # Ensure trip isn't already completed
        if trip.is_completed:
            return Response(
                {'detail': 'Trip is already completed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure the requester is the driver or an admin
        if (trip.driver.user != request.user and
                not request.user.is_staff and
                request.user.user_type != 'admin'):
            return Response(
                {'detail': 'You do not have permission to end this trip'},
                status=status.HTTP_403_FORBIDDEN
            )

        # End the trip
        TripService.end_trip(trip.id)

        # Return updated trip
        serializer = self.get_serializer(trip)
        return Response(serializer.data)

class AnomalyViewSet(BaseModelViewSet):
    """
    API endpoint for anomalies.
    """
    queryset = Anomaly.objects.all()
    serializer_class = AnomalySerializer
    filterset_class = AnomalyFilter
    service_class = AnomalyService

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create']:
            return [IsDriverOrAdmin()]
        if self.action in ['update', 'partial_update', 'destroy', 'resolve']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return AnomalyCreateSerializer
        if self.action == 'resolve':
            return AnomalyResolveSerializer
        return AnomalySerializer

    def get_queryset(self):
        """
        Filter anomalies based on parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Filter by trip if provided
        trip_id = self.request.query_params.get('trip_id')
        if trip_id:
            queryset = queryset.filter(trip_id=trip_id)

        # Filter by type if provided
        anomaly_type = self.request.query_params.get('type')
        if anomaly_type:
            queryset = queryset.filter(type=anomaly_type)

        # Filter by severity if provided
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by resolution status if provided
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            queryset = queryset.filter(resolved=resolved == 'true')

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """
        Create an anomaly for the driver's bus.
        """
        # Get bus ID and trip ID based on user type
        if self.request.user.user_type == 'driver':
            # Get bus ID from driver
            from apps.drivers.selectors import get_driver_by_user
            driver = get_driver_by_user(self.request.user.id)

            # Get the driver's buses
            from apps.buses.selectors import get_buses_by_driver
            buses = get_buses_by_driver(driver.id)

            if not buses:
                return Response(
                    {'detail': 'No buses found for this driver'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Use the first bus
            bus = buses.first()

            # Get active trip
            from apps.tracking.selectors import get_active_trip
            trip = get_active_trip(bus.id)
            trip_id = trip.id if trip else None
        else:
            # Admin must specify bus ID
            bus_id = self.request.data.get('bus_id')
            if not bus_id:
                return Response(
                    {'detail': 'Bus ID is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get bus
            from apps.buses.selectors import get_bus_by_id
            bus = get_bus_by_id(bus_id)

            # Get trip ID if provided
            trip_id = self.request.data.get('trip_id')

        # Create anomaly
        AnomalyService.create_anomaly(
            bus_id=bus.id,
            trip_id=trip_id,
            **serializer.validated_data
        )

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        Resolve an anomaly.
        """
        anomaly = self.get_object()

        # Ensure anomaly isn't already resolved
        if anomaly.resolved:
            return Response(
                {'detail': 'Anomaly is already resolved'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolve the anomaly
        AnomalyService.resolve_anomaly(
            anomaly_id=anomaly.id,
            resolution_notes=serializer.validated_data.get('resolution_notes', '')
        )

        # Return updated anomaly
        updated_serializer = AnomalySerializer(anomaly)
        return Response(updated_serializer.data)