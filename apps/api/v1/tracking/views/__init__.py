"""
Views for the tracking API with comprehensive documentation.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from apps.api.viewsets import BaseModelViewSet, ReadOnlyModelViewSet
from apps.core.permissions import IsAdmin, IsApprovedDriver, IsDriverOrAdmin
from apps.tracking.models import (
    Anomaly,
    BusLine,
    BusWaitingList,
    CurrencyTransaction,
    DriverPerformanceScore,
    LocationUpdate,
    PassengerCount,
    PremiumFeature,
    ReputationScore,
    Trip,
    UserPremiumFeature,
    VirtualCurrency,
    WaitingCountReport,
    WaitingPassengers,
)
from apps.tracking.services import (
    AnomalyService,
    BusLineService,
    LocationUpdateService,
    PassengerCountService,
    ReputationService,
    TripService,
    VirtualCurrencyService,
    WaitingListService,
    WaitingReportService,
)
from apps.tracking.services.driver_services import (
    DriverCurrencyService,
    DriverPerformanceService,
    PremiumFeatureService,
)

from ..filters import (
    AnomalyFilter,
    BusLineFilter,
    LocationUpdateFilter,
    PassengerCountFilter,
    TripFilter,
    WaitingPassengersFilter,
)
from ..serializers import (
    AnomalyCreateSerializer,
    AnomalyResolveSerializer,
    AnomalySerializer,
    BusLineCreateSerializer,
    BusLineSerializer,
    BusWaitingListCreateSerializer,
    BusWaitingListSerializer,
    CurrencyTransactionSerializer,
    DriverCurrencyTransactionSerializer,
    DriverPerformanceScoreSerializer,
    DriverStatsSerializer,
    EstimateArrivalTimeSerializer,
    JoinWaitingListSerializer,
    LeaveWaitingListSerializer,
    LocationUpdateCreateSerializer,
    LocationUpdateSerializer,
    PassengerCountCreateSerializer,
    PassengerCountSerializer,
    PremiumFeatureSerializer,
    PurchasePremiumFeatureSerializer,
    ReputationScoreSerializer,
    StartTrackingSerializer,
    StopTrackingSerializer,
    TripCreateSerializer,
    TripSerializer,
    TripUpdateSerializer,
    UserPremiumFeatureSerializer,
    VirtualCurrencySerializer,
    WaitingCountReportCreateSerializer,
    WaitingCountReportSerializer,
    WaitingCountReportVerifySerializer,
    WaitingListSummarySerializer,
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
        from rest_framework.exceptions import ValidationError as DRFValidationError

        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(self.request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            raise DRFValidationError({'detail': 'No buses found for this driver'})

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
        location = LocationUpdateService.record_location_update(
            bus_id=bus.id,
            **serializer.validated_data
        )
        serializer.instance = location

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
        from rest_framework.exceptions import ValidationError as DRFValidationError

        # Get bus ID from driver
        from apps.drivers.selectors import get_driver_by_user
        driver = get_driver_by_user(self.request.user.id)

        # Get the driver's buses
        from apps.buses.selectors import get_buses_by_driver
        buses = get_buses_by_driver(driver.id)

        if not buses:
            raise DRFValidationError({'detail': 'No buses found for this driver'})

        # Use the first bus (can be enhanced to select a specific bus)
        bus = buses.first()

        # Validate passenger count against bus capacity
        count = serializer.validated_data.get('count', 0)
        if bus and bus.capacity and count > bus.capacity * 2:
            raise DRFValidationError({'count': f'Passenger count ({count}) exceeds maximum allowed ({bus.capacity * 2}).'})

        # Create passenger count (service handles trip/line internally)
        passenger_count = PassengerCountService.update_passenger_count(
            bus_id=bus.id,
            **serializer.validated_data
        )
        serializer.instance = passenger_count

_WAITING_PASSENGERS_DEPRECATED_HEADERS = {
    'X-Deprecated-API': 'true',
    'X-Deprecation-Notice': (
        'WaitingPassengers is deprecated. Use /api/v1/tracking/waiting-reports/ instead.'
    ),
}


class WaitingPassengersViewSet(BaseModelViewSet):
    """
    API endpoint for waiting passengers.

    DEPRECATED: This endpoint is superseded by /api/v1/tracking/waiting-reports/
    which supports verification, trust scores, and gamification. This model is
    retained for backward compatibility only — no new consumers should use it.
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

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        for key, value in _WAITING_PASSENGERS_DEPRECATED_HEADERS.items():
            response[key] = value
        return response

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        for key, value in _WAITING_PASSENGERS_DEPRECATED_HEADERS.items():
            response[key] = value
        return response

    def perform_create(self, serializer):
        """
        Create a waiting passengers report.
        """
        PassengerCountService.update_waiting_passengers(
            stop_id=serializer.validated_data['stop'].id,
            count=serializer.validated_data['count'],
            line_id=serializer.validated_data.get('line').id if serializer.validated_data.get('line') else None,
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
        if self.action in ['list', 'retrieve', 'statistics', 'history']:
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

    def perform_create(self, serializer):
        """
        Create a trip, enforcing no concurrent active trips on the same bus
        and verifying the requesting driver owns the bus.
        Uses select_for_update() to prevent race conditions under concurrent requests.
        """
        from django.db import transaction as _tx
        from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied
        from apps.buses.models import Bus as BusModel

        bus = serializer.validated_data.get('bus')

        with _tx.atomic():
            if bus:
                # Lock the bus row to prevent concurrent trip creation
                bus = BusModel.objects.select_for_update().get(id=bus.id)

            # Check for existing active trip on this bus
            if bus and Trip.objects.filter(bus=bus, is_completed=False).exists():
                raise DRFValidationError({'bus': 'This bus already has an active trip.'})

            # Check driver owns this bus (skip for admins)
            if bus and hasattr(self.request.user, 'driver'):
                if bus.driver != self.request.user.driver:
                    raise PermissionDenied('You are not authorized to use this bus.')

            super().perform_create(serializer)

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

        # Refresh instance so is_completed reflects the committed state
        trip.refresh_from_db()

        # Return updated trip
        serializer = self.get_serializer(trip)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Get trip history for the authenticated user.
        
        This endpoint returns a paginated list of trips based on user type:
        - Drivers: Returns their own trip history
        - Passengers: Returns trips they've taken
        - Admins: Can see all trips
        
        Query parameters:
        - limit: Number of results to return (default: 20, max: 100)
        - offset: Number of results to skip for pagination
        - is_completed: Filter by completion status (true/false)
        - start_date: Filter trips after this date (YYYY-MM-DD)
        - end_date: Filter trips before this date (YYYY-MM-DD)
        - line_id: Filter by specific line
        - ordering: Order results by field (e.g., '-start_time' for newest first)
        
        Returns paginated trip history with trip details.
        """
        # Get queryset based on user type
        queryset = self.get_queryset()
        
        # Additional filtering for non-admin users
        if not request.user.is_staff and request.user.user_type != 'admin':
            if request.user.user_type == 'driver':
                # Drivers see their own trips
                try:
                    from apps.drivers.models import Driver
                    driver = Driver.objects.get(user=request.user)
                    queryset = queryset.filter(driver=driver)
                except Driver.DoesNotExist:
                    queryset = queryset.none()
            else:
                # Passengers would see trips they've taken (need to implement passenger tracking)
                # For now, return empty queryset for passengers
                queryset = queryset.none()
        
        # Apply ordering (newest first by default)
        ordering = request.query_params.get('ordering', '-start_time')
        queryset = queryset.order_by(ordering)
        
        # Handle limit parameter
        limit = request.query_params.get('limit', '20')
        try:
            limit = min(int(limit), 100)  # Max 100 results
        except (ValueError, TypeError):
            limit = 20
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        # If no pagination, apply limit manually
        queryset = queryset[:limit]
        serializer = self.get_serializer(queryset, many=True)
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
            return [IsAuthenticated()]
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
        Create an anomaly.

        Drivers use their own bus automatically; admins must supply bus_id.
        Passengers must supply bus_id to identify the bus they are reporting.
        The reporting user is stored in reported_by for audit purposes.
        """
        from rest_framework.exceptions import ValidationError as DRFValidationError

        # Determine bus and active trip based on user type
        if self.request.user.user_type == 'driver':
            # Drivers report against their own bus
            from apps.drivers.selectors import get_driver_by_user
            driver = get_driver_by_user(self.request.user.id)

            from apps.buses.selectors import get_buses_by_driver
            buses = get_buses_by_driver(driver.id)

            if not buses:
                raise DRFValidationError({'detail': 'No buses found for this driver'})

            bus = buses.first()

            from apps.tracking.selectors import get_active_trip
            trip = get_active_trip(bus.id)
            trip_id = trip.id if trip else None
        else:
            # Admins and passengers must supply bus_id
            bus_id = self.request.data.get('bus_id')
            if not bus_id:
                raise DRFValidationError({'detail': 'Bus ID is required'})

            from apps.buses.selectors import get_bus_by_id
            bus = get_bus_by_id(bus_id)

            trip_id = self.request.data.get('trip_id')

        # Create anomaly and record who reported it
        validated = serializer.validated_data.copy()
        anomaly = AnomalyService.create_anomaly(
            bus_id=bus.id,
            anomaly_type=validated.pop('type'),
            description=validated.pop('description'),
            trip_id=trip_id,
            reported_by_id=self.request.user.id,
            **validated
        )
        serializer.instance = anomaly

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


class BusWaitingListViewSet(BaseModelViewSet):
    """
    API endpoint for bus waiting lists.
    """
    queryset = BusWaitingList.objects.all()
    serializer_class = BusWaitingListSerializer
    
    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ['list', 'retrieve', 'summary']:
            return [IsAuthenticated()]
        if self.action in ['create', 'join', 'leave']:
            return [IsAuthenticated()]
        return [IsAdmin()]
    
    def get_serializer_class(self):
        """Get serializer based on action."""
        if self.action == 'create':
            return BusWaitingListCreateSerializer
        if self.action == 'join':
            return JoinWaitingListSerializer
        if self.action == 'leave':
            return LeaveWaitingListSerializer
        return BusWaitingListSerializer
    
    def get_queryset(self):
        """Filter queryset based on parameters."""
        queryset = super().get_queryset()
        
        # Filter by user's own waiting lists by default
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by stop
        stop_id = self.request.query_params.get('stop_id')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.select_related('bus', 'stop', 'user').order_by('-joined_at')
    
    @action(detail=False, methods=['post'])
    def join(self, request):
        """Join a waiting list."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        waiting_list = WaitingListService.join_waiting_list(
            user_id=str(request.user.id),
            bus_id=str(serializer.validated_data['bus_id']),
            stop_id=str(serializer.validated_data['stop_id'])
        )
        
        response_serializer = BusWaitingListSerializer(waiting_list, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def leave(self, request):
        """Leave a waiting list."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        waiting_list = WaitingListService.leave_waiting_list(
            user_id=str(request.user.id),
            waiting_list_id=str(serializer.validated_data['waiting_list_id']),
            reason=serializer.validated_data.get('reason', 'other')
        )
        
        response_serializer = BusWaitingListSerializer(waiting_list, context={'request': request})
        return Response(response_serializer.data)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get waiting list summary for a stop."""
        stop_id = request.query_params.get('stop_id')
        if not stop_id:
            return Response(
                {'detail': 'stop_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        summaries = WaitingListService.get_stop_summary(stop_id)
        serializer = WaitingListSummarySerializer(summaries, many=True)
        return Response(serializer.data)


class WaitingCountReportViewSet(BaseModelViewSet):
    """
    API endpoint for waiting count reports.
    """
    queryset = WaitingCountReport.objects.all()
    serializer_class = WaitingCountReportSerializer
    
    def get_permissions(self):
        """Get permissions based on action."""
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action == 'verify':
            return [IsApprovedDriver()]
        return [IsDriverOrAdmin()]
    
    def get_serializer_class(self):
        """Get serializer based on action."""
        if self.action == 'create':
            return WaitingCountReportCreateSerializer
        if self.action == 'verify':
            return WaitingCountReportVerifySerializer
        return WaitingCountReportSerializer
    
    def get_queryset(self):
        """Filter queryset based on parameters."""
        queryset = super().get_queryset()
        
        # Filter by stop
        stop_id = self.request.query_params.get('stop_id')
        if stop_id:
            queryset = queryset.filter(stop_id=stop_id)
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by line
        line_id = self.request.query_params.get('line_id')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by verification status
        verification_status = self.request.query_params.get('verification_status')
        if verification_status:
            queryset = queryset.filter(verification_status=verification_status)
        
        # Filter by reporter (for users to see their own reports)
        if not self.request.user.is_staff:
            show_own = self.request.query_params.get('own', 'false').lower() == 'true'
            if show_own:
                queryset = queryset.filter(reporter=self.request.user)
        
        return queryset.select_related('reporter', 'stop', 'bus', 'line').order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create a waiting count report."""
        validated = serializer.validated_data.copy()
        # Convert model instances to IDs for service layer
        stop = validated.pop('stop')
        bus = validated.pop('bus', None)
        line = validated.pop('line', None)
        report = WaitingReportService.create_report(
            reporter_id=str(self.request.user.id),
            stop_id=str(stop.id),
            bus_id=str(bus.id) if bus else None,
            line_id=str(line.id) if line else None,
            **validated
        )
        serializer.instance = report
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Verify a waiting count report (driver only)."""
        report = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        verified_report = WaitingReportService.verify_report(
            report_id=str(report.id),
            verifier_id=str(request.user.id),
            **serializer.validated_data
        )
        
        response_serializer = WaitingCountReportSerializer(verified_report, context={'request': request})
        return Response(response_serializer.data)


class ReputationScoreViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for reputation scores (read-only).
    """
    queryset = ReputationScore.objects.all()
    serializer_class = ReputationScoreSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter queryset based on parameters."""
        queryset = super().get_queryset()
        
        # Users can only see their own reputation unless admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset.select_related('user')
    
    @action(detail=False, methods=['get'])
    def my_stats(self, request):
        """Get current user's reputation statistics."""
        stats = ReputationService.get_reputation_stats(str(request.user.id))
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get reputation leaderboard."""
        # Get top reputation users
        top_users = ReputationScore.objects.filter(
            total_reports__gte=10  # Minimum 10 reports to be on leaderboard
        ).select_related('user').order_by('-trust_multiplier', '-correct_reports')[:20]
        
        leaderboard = []
        for i, reputation in enumerate(top_users):
            leaderboard.append({
                'rank': i + 1,
                'user_name': reputation.user.get_full_name() or reputation.user.first_name,
                'reputation_level': reputation.reputation_level,
                'accuracy_rate': reputation.accuracy_rate,
                'total_reports': reputation.total_reports,
                'trust_multiplier': float(reputation.trust_multiplier)
            })
        
        return Response(leaderboard)


class VirtualCurrencyViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for virtual currency (read-only).
    """
    queryset = VirtualCurrency.objects.all()
    serializer_class = VirtualCurrencySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter queryset based on parameters."""
        queryset = super().get_queryset()
        
        # Users can only see their own currency unless admin
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset.select_related('user')
    
    @action(detail=False, methods=['get'])
    def my_balance(self, request):
        """Get current user's currency balance."""
        currency = VirtualCurrencyService.get_or_create_currency(str(request.user.id))
        serializer = self.get_serializer(currency)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get current user's currency transactions."""
        transactions = CurrencyTransaction.objects.filter(
            user=request.user
        ).order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(transactions)
        if page is not None:
            serializer = CurrencyTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CurrencyTransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get virtual currency leaderboard."""
        period = request.query_params.get('period', 'weekly')
        limit = int(request.query_params.get('limit', 10))
        
        leaderboard = VirtualCurrencyService.get_leaderboard(period=period, limit=limit)
        return Response({
            'period': period,
            'leaderboard': leaderboard
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Driver Performance Scores",
        description="""
        **Driver Performance Tracking System**
        
        Get driver performance data including safety scores, on-time performance, and level progression.
        The system tracks driver performance across 4 levels: Rookie → Experienced → Expert → Master.
        
        **Context**: This is part of the Bus Tracker's driver gamification system where drivers earn 
        virtual currency based on their performance metrics and can unlock premium features.
        
        **Workflow**: Performance data is automatically updated when drivers complete trips, 
        verify passenger reports, and maintain safety standards.
        
        **Permissions**: 
        - Drivers can only view their own performance data
        - Admins can view all driver performances
        - Regular passengers cannot access this endpoint
        """,
        responses={
            200: DriverPerformanceScoreSerializer(many=True),
            403: OpenApiResponse(description="Access denied for non-drivers"),
        },
        tags=["Driver Performance"]
    ),
    retrieve=extend_schema(
        summary="Get Driver Performance Details",
        description="Get detailed performance metrics for a specific driver including all scoring components.",
        tags=["Driver Performance"]
    ),
)
class DriverPerformanceScoreViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for comprehensive driver performance tracking and gamification.
    
    This ViewSet provides access to the driver performance scoring system that forms
    the foundation of the bus tracker's gamification features. Drivers progress through
    4 performance levels based on their safety, punctuality, and service quality.
    """
    queryset = DriverPerformanceScore.objects.select_related('driver__user')
    serializer_class = DriverPerformanceScoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter performance scores based on user permissions."""
        queryset = super().get_queryset()
        
        if self.request.user.user_type == 'driver':
            # Drivers can only see their own performance
            try:
                from apps.drivers.models import Driver
                driver = Driver.objects.get(user=self.request.user)
                return queryset.filter(driver=driver)
            except Driver.DoesNotExist:
                return queryset.none()
        elif self.request.user.is_admin:
            # Admins can see all performances
            return queryset
        else:
            # Regular users cannot see performance scores
            return queryset.none()

    @extend_schema(
        summary="Driver Performance Leaderboard",
        description="""
        **Driver Performance Leaderboard**
        
        Get the top-performing drivers ranked by safety score, passenger rating, and total trips.
        This leaderboard motivates drivers to maintain high performance standards and compete
        in a healthy way for better rankings.
        
        **Ranking Criteria** (in order of importance):
        1. Safety Score (0-100)
        2. Passenger Rating (1-5 stars)
        3. Total Trips Completed
        
        **Use Case**: Display in driver dashboard and public leaderboards to encourage
        competitive improvement and recognize top performers.
        """,
        parameters=[
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of top drivers to return (default: 10, max: 50)',
                default=10
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Leaderboard data with driver rankings",
                examples=[{
                    "leaderboard": [
                        {
                            "rank": 1,
                            "driver_name": "Ahmed Benaissa",
                            "performance_level": "expert",
                            "safety_score": 98.5,
                            "passenger_rating": 4.8,
                            "on_time_percentage": 95.2,
                            "total_trips": 156
                        }
                    ],
                    "total_drivers": 45
                }]
            )
        },
        tags=["Driver Performance"]
    )
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get driver performance leaderboard."""
        limit = int(request.query_params.get('limit', 10))
        leaderboard = DriverPerformanceService.get_driver_leaderboard(limit)
        return Response({
            'leaderboard': leaderboard,
            'total_drivers': DriverPerformanceScore.objects.count()
        })

    @extend_schema(
        summary="My Driver Performance Dashboard",
        description="""
        **Complete Driver Performance Dashboard**
        
        Get comprehensive performance statistics for the authenticated driver including:
        
        **Performance Metrics**:
        - Current performance level (Rookie/Experienced/Expert/Master)
        - Safety score, passenger rating, on-time percentage
        - Trip statistics and streaks
        
        **Virtual Currency Data**:
        - Current coin balance and lifetime earnings
        - Recent transaction history
        - Earnings breakdown by activity type
        
        **Premium Features**:
        - Currently active premium subscriptions
        - Available features for purchase
        - Feature access status and expiration dates
        
        **Workflow Context**: This endpoint serves as the main driver dashboard,
        providing all necessary information for drivers to track their progress,
        manage their virtual currency, and access premium features.
        
        **Access**: Only available to authenticated drivers with approved status.
        """,
        responses={
            200: OpenApiResponse(
                description="Complete driver dashboard data",
                examples=[{
                    "performance_score": {
                        "performance_level": "experienced",
                        "total_trips": 42,
                        "on_time_percentage": 85.7,
                        "safety_score": "94.50",
                        "passenger_rating": "4.30"
                    },
                    "virtual_currency": {
                        "balance": 1250,
                        "lifetime_earned": 3200,
                        "lifetime_spent": 1950
                    },
                    "active_premium_features": [
                        {
                            "id": "uuid",
                            "feature_details": {
                                "name": "Advanced Route Analytics",
                                "feature_type": "route_analytics"
                            },
                            "expires_at": "2024-03-15T10:30:00Z",
                            "days_remaining": 12
                        }
                    ],
                    "earnings_summary": {
                        "total_earned": 450,
                        "transaction_count": 15,
                        "period_days": 30
                    }
                }]
            ),
            403: OpenApiResponse(description="Access denied - not a driver"),
            404: OpenApiResponse(description="Driver profile not found"),
        },
        tags=["Driver Performance"]
    )
    @action(detail=False, methods=['get'])
    def my_stats(self, request):
        """Get current driver's performance statistics."""
        if not request.user.is_driver:
            return Response(
                {'detail': 'Only drivers can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            from apps.drivers.models import Driver
            driver = Driver.objects.get(user=request.user)
            performance = DriverPerformanceService.get_or_create_performance_score(driver)
            
            # Get currency data
            try:
                currency = VirtualCurrency.objects.get(user=request.user)
            except VirtualCurrency.DoesNotExist:
                currency = None
            
            # Get active premium features
            active_features = UserPremiumFeature.objects.filter(
                user=request.user,
                is_active=True
            ).select_related('feature')
            
            # Get recent transactions
            recent_transactions = CurrencyTransaction.objects.filter(
                user=request.user
            ).order_by('-created_at')[:10]
            
            # Get available features
            available_features = PremiumFeatureService.get_available_features_for_user(request.user)
            
            # Get earnings summary
            earnings_summary = DriverCurrencyService.get_driver_earnings_summary(request.user)
            
            perf_data = DriverPerformanceScoreSerializer(performance).data
            data = {
                **perf_data,  # Flatten performance fields to top level
                'virtual_currency': VirtualCurrencySerializer(currency).data if currency else None,
                'active_premium_features': UserPremiumFeatureSerializer(active_features, many=True).data,
                'recent_transactions': DriverCurrencyTransactionSerializer(recent_transactions, many=True).data,
                'available_features': PremiumFeatureSerializer(available_features, many=True).data,
                'earnings_summary': earnings_summary,
            }
            
            return Response(data)
            
        except Driver.DoesNotExist:
            return Response(
                {'detail': 'Driver profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema_view(
    list=extend_schema(
        summary="List All Premium Features",
        description="""
        **Premium Features Marketplace**
        
        Browse all available premium features in the bus tracker system. Features are 
        automatically filtered based on user type and current subscriptions.
        
        **Feature Categories**:
        - **Driver Features**: Route analytics, fuel optimization, priority support
        - **Universal Features**: Ad-free experience, dark mode, custom notifications
        - **Passenger Features**: Priority notifications, custom dashboard
        
        **Context**: Part of the virtual currency system where users can spend earned
        coins to unlock premium functionality and enhanced app experiences.
        
        **Business Model**: Drivers earn coins through performance, passengers through
        app engagement and accurate reporting. Coins can only be spent within the app.
        """,
        responses={
            200: PremiumFeatureSerializer(many=True),
        },
        tags=["Premium Features"]
    ),
    retrieve=extend_schema(
        summary="Get Premium Feature Details",
        description="Get detailed information about a specific premium feature including requirements and benefits.",
        tags=["Premium Features"]
    ),
)
class PremiumFeatureViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for premium features marketplace and subscription system.
    
    This ViewSet manages the premium features that users can purchase with virtual currency.
    Features are categorized by target user type and include various app enhancements
    and exclusive functionalities.
    """
    queryset = PremiumFeature.objects.filter(is_active=True)
    serializer_class = PremiumFeatureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter features based on user type."""
        queryset = super().get_queryset()
        
        # Filter by target users
        if self.request.user.is_driver:
            queryset = queryset.filter(
                target_users__in=['drivers', 'all']
            )
        else:
            queryset = queryset.filter(
                target_users__in=['passengers', 'all']
            )
        
        return queryset

    @extend_schema(
        summary="Get Available Premium Features",
        description="""
        **Personalized Feature Recommendations**
        
        Get premium features available for purchase by the current user, automatically
        filtered based on:
        
        **Filtering Criteria**:
        - User type (driver/passenger)
        - Performance level requirements (for drivers)
        - Currently active subscriptions (excluded)
        - Feature prerequisites and eligibility
        
        **Driver-Specific Logic**:
        - Rookie drivers see basic features
        - Expert/Master drivers unlock advanced analytics
        - Features may require minimum trip count or safety score
        
        **Use Case**: Display in the app's premium features store with personalized
        recommendations based on user profile and achievements.
        
        **Response**: Only features the user can actually purchase and hasn't already bought.
        """,
        responses={
            200: OpenApiResponse(
                description="Available premium features for current user",
                examples=[{
                    "available_features": [
                        {
                            "id": "uuid",
                            "name": "Advanced Route Analytics",
                            "feature_type": "route_analytics",
                            "description": "Detailed trip analytics and performance insights",
                            "cost_coins": 500,
                            "duration_days": 30,
                            "target_users": "drivers",
                            "required_level": "experienced"
                        }
                    ]
                }]
            )
        },
        tags=["Premium Features"]
    )
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get features available for current user."""
        features = PremiumFeatureService.get_available_features_for_user(request.user)
        serializer = PremiumFeatureSerializer(features, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Purchase Premium Feature",
        description="""
        **Premium Feature Purchase System**
        
        Purchase a premium feature using virtual currency coins. This endpoint handles
        the complete purchase workflow with comprehensive validation.
        
        **Purchase Process**:
        1. Validate user has sufficient coin balance
        2. Check feature eligibility (level requirements, etc.)
        3. Verify feature is not already owned and active
        4. Deduct coins from user's virtual currency account
        5. Create feature subscription with expiration date
        6. Return purchase confirmation with details
        
        **Validation Checks**:
        - Sufficient virtual currency balance
        - User meets feature requirements (performance level, etc.)
        - Feature is active and purchasable
        - User doesn't already own active subscription
        
        **Transaction Safety**: Uses database transactions to ensure atomicity.
        If any step fails, the entire purchase is rolled back.
        
        **Business Logic**: This is the core monetization endpoint where users spend
        their earned virtual currency on premium app features and enhancements.
        """,
        request=PurchasePremiumFeatureSerializer,
        responses={
            201: OpenApiResponse(
                description="Feature purchased successfully",
                examples=[{
                    "message": "Feature purchased successfully",
                    "purchase": {
                        "id": "uuid",
                        "feature_details": {
                            "name": "Advanced Route Analytics",
                            "feature_type": "route_analytics"
                        },
                        "expires_at": "2024-03-15T10:30:00Z",
                        "coins_spent": 500,
                        "is_active": True,
                        "days_remaining": 30
                    },
                    "expires_at": "2024-03-15T10:30:00Z"
                }]
            ),
            400: OpenApiResponse(
                description="Purchase failed",
                examples=[{
                    "error": "Insufficient balance. Need 500 coins, have 250"
                }, {
                    "error": "Feature already owned and active"
                }, {
                    "error": "Premium feature not found"
                }]
            )
        },
        tags=["Premium Features"]
    )
    @action(detail=False, methods=['post'])
    def purchase(self, request):
        """Purchase a premium feature."""
        serializer = PurchasePremiumFeatureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = PremiumFeatureService.purchase_feature(
            request.user,
            serializer.validated_data['feature_id']
        )
        
        if result['success']:
            return Response({
                'message': 'Feature purchased successfully',
                'purchase': UserPremiumFeatureSerializer(result['purchase']).data,
                'expires_at': result['expires_at']
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(
        summary="List User's Premium Features",
        description="""
        **User Premium Feature Subscriptions**
        
        Get all premium features purchased by the current user, including both active
        and expired subscriptions with full history.
        
        **Subscription Status**:
        - **Active**: Currently usable features
        - **Expired**: Past subscriptions that have reached expiration
        - **Deactivated**: Manually disabled features
        
        **Use Case**: Display in user profile/settings to show purchase history,
        active subscriptions, and expiration dates for renewal planning.
        
        **Auto-Management**: Expired features are automatically deactivated
        when accessed to maintain data consistency.
        """,
        responses={
            200: UserPremiumFeatureSerializer(many=True),
        },
        tags=["User Premium Features"]
    ),
    retrieve=extend_schema(
        summary="Get Premium Feature Subscription Details",
        description="Get detailed information about a specific premium feature subscription including usage stats.",
        tags=["User Premium Features"]
    ),
)
class UserPremiumFeatureViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for managing user's premium feature subscriptions and access control.
    
    This ViewSet provides comprehensive management of user premium feature subscriptions,
    including access verification, expiration handling, and subscription history.
    """
    serializer_class = UserPremiumFeatureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get current user's premium features."""
        return UserPremiumFeature.objects.filter(
            user=self.request.user
        ).select_related('feature').order_by('-purchased_at')

    @extend_schema(
        summary="Get Active Premium Features",
        description="""
        **Active Premium Feature Dashboard**
        
        Get only the currently active and non-expired premium features for the user.
        This endpoint automatically manages feature expiration and provides real-time
        access status.
        
        **Automatic Expiration Handling**:
        - Checks expiration dates in real-time
        - Automatically deactivates expired features
        - Returns only truly active subscriptions
        
        **Feature Status Indicators**:
        - Days remaining until expiration
        - Active/inactive status
        - Auto-renewal information (if applicable)
        
        **Use Case**: Primary endpoint for the app to check which premium features
        the user has access to. Used for UI rendering, feature gating, and displaying
        active subscription status.
        
        **Performance**: Optimized for frequent access as it's called regularly
        by the client app to determine feature availability.
        """,
        responses={
            200: OpenApiResponse(
                description="Currently active premium features",
                examples=[{
                    "active_features": [
                        {
                            "id": "uuid",
                            "feature_details": {
                                "name": "Advanced Route Analytics",
                                "feature_type": "route_analytics",
                                "description": "Detailed analytics and insights"
                            },
                            "expires_at": "2024-03-15T10:30:00Z",
                            "days_remaining": 12,
                            "is_active": True,
                            "coins_spent": 500
                        }
                    ]
                }]
            )
        },
        tags=["User Premium Features"]
    )
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get user's active premium features."""
        features = self.get_queryset().filter(is_active=True)
        
        # Update expired features
        for feature in features:
            feature.deactivate_if_expired()
        
        # Re-filter for truly active features
        active_features = features.filter(is_active=True)
        serializer = self.get_serializer(active_features, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Check Feature Access",
        description="""
        **Real-time Feature Access Verification**
        
        Verify if the user has active access to a specific feature type. This endpoint
        provides real-time access control for premium features throughout the app.
        
        **Access Verification Process**:
        1. Check if user has purchased the feature type
        2. Verify subscription is still active
        3. Confirm feature hasn't expired
        4. Auto-deactivate if expired
        5. Return access status
        
        **Feature Types**: Use the exact feature_type from the PremiumFeature model:
        - `route_analytics` - Advanced route and trip analytics
        - `priority_support` - Priority customer support access
        - `custom_dashboard` - Customizable dashboard features
        - `fuel_optimization` - Fuel efficiency tools and tips
        - `real_time_feedback` - Real-time passenger feedback
        
        **Security**: This is a critical endpoint for feature gating and access control
        throughout the application. Always verify access before exposing premium features.
        """,
        request=OpenApiParameter(
            name='feature_type',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='The feature type to check access for',
            required=True,
            examples=['route_analytics', 'priority_support', 'custom_dashboard']
        ),
        responses={
            200: OpenApiResponse(
                description="Feature access status",
                examples=[{
                    "has_access": True,
                    "feature_type": "route_analytics"
                }, {
                    "has_access": False,
                    "feature_type": "premium_support"
                }]
            ),
            400: OpenApiResponse(
                description="Missing or invalid feature type",
                examples=[{
                    "error": "feature_type is required"
                }]
            )
        },
        tags=["User Premium Features"]
    )
    @action(detail=True, methods=['post'])
    def check_access(self, request, pk=None):
        """Check if user has access to a specific feature type."""
        feature_type = request.data.get('feature_type')
        if not feature_type:
            return Response(
                {'error': 'feature_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        has_access = PremiumFeatureService.check_feature_access(
            request.user, 
            feature_type
        )
        
        return Response({
            'has_access': has_access,
            'feature_type': feature_type
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Driver Currency Accounts",
        description="""
        **Driver Virtual Currency System Overview**
        
        Access the virtual currency system designed specifically for bus drivers.
        This is part of the comprehensive driver gamification system where drivers
        earn coins through performance and can spend them on premium features.
        
        **Earning Mechanisms**:
        - Trip completion bonuses (base: 50 coins)
        - On-time performance bonuses (+25 coins)
        - Performance level multipliers (1.0x to 2.0x)
        - Safety record bonuses
        - Passenger report verification accuracy
        - Weekly streak bonuses
        
        **Spending Options**:
        - Premium route analytics (500 coins)
        - Advanced dashboard features (600 coins)
        - Priority customer support (750 coins)
        - Fuel optimization tools (400 coins)
        - Ad-free experience (200 coins)
        
        **Context**: Virtual currency can only be spent within the app ecosystem,
        creating a closed-loop economy that incentivizes driver performance.
        """,
        responses={
            200: VirtualCurrencySerializer(many=True),
        },
        tags=["Driver Virtual Currency"]
    ),
)
class DriverCurrencyViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for driver virtual currency management and gamification system.
    
    This ViewSet provides comprehensive access to the driver virtual currency system,
    including balance tracking, transaction history, earnings analytics, and leaderboards.
    The system incentivizes driver performance through a sophisticated reward mechanism.
    """
    serializer_class = VirtualCurrencySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get currency for current user only."""
        return VirtualCurrency.objects.filter(user=self.request.user)

    @extend_schema(
        summary="Get Driver Currency Balance",
        description="""
        **Driver Virtual Currency Balance Dashboard**
        
        Get the current virtual currency balance and lifetime statistics for the authenticated driver.
        This is the primary endpoint for checking available spending power in the app.
        
        **Balance Information**:
        - **Current Balance**: Available coins for spending
        - **Lifetime Earned**: Total coins earned through performance
        - **Lifetime Spent**: Total coins spent on premium features
        - **Last Transaction**: Most recent currency activity
        
        **Earning Activities Tracked**:
        - `route_completion` - Trip completion bonuses
        - `on_time_performance` - Punctuality bonuses
        - `verification_accuracy` - Report verification rewards
        - `safety_bonus` - Safe driving incentives
        - `achievement_unlock` - Milestone rewards
        - `admin_adjustment` - Manual adjustments
        
        **Use Case**: Primary currency dashboard for drivers to track their virtual
        wealth and make informed decisions about premium feature purchases.
        
        **Auto-Creation**: If no currency account exists, returns zero values.
        The account will be created automatically on first earning activity.
        """,
        responses={
            200: OpenApiResponse(
                description="Driver's virtual currency balance and statistics",
                examples=[{
                    "balance": 1250,
                    "lifetime_earned": 3200,
                    "lifetime_spent": 1950,
                    "last_transaction": "2024-02-14T09:30:00Z",
                    "created_at": "2024-01-15T08:00:00Z",
                    "updated_at": "2024-02-14T09:30:00Z"
                }]
            )
        },
        tags=["Driver Virtual Currency"]
    )
    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get current user's currency balance."""
        try:
            currency = VirtualCurrency.objects.get(user=request.user)
            serializer = VirtualCurrencySerializer(currency)
            return Response(serializer.data)
        except VirtualCurrency.DoesNotExist:
            return Response({
                'balance': 0,
                'lifetime_earned': 0,
                'lifetime_spent': 0,
                'last_transaction': None
            })

    @extend_schema(
        summary="Get Currency Transaction History",
        description="""
        **Virtual Currency Transaction History**
        
        Get detailed transaction history showing how coins were earned and spent.
        This provides full transparency and accountability for all currency movements.
        
        **Transaction Types**:
        
        **Earning Transactions** (positive amounts):
        - `route_completion` - Base trip completion reward
        - `on_time_performance` - Punctuality bonus
        - `verification_accuracy` - Accurate report verification
        - `safety_bonus` - Safe driving rewards
        - `achievement_unlock` - Milestone achievements
        - `streak_bonus` - Consecutive performance bonuses
        
        **Spending Transactions** (negative amounts):
        - `premium_purchase` - Premium feature purchases
        - `admin_adjustment` - Administrative corrections
        
        **Query Parameters**:
        - `limit`: Number of transactions to return (default: 20)
        - `type`: Filter by transaction type
        
        **Use Case**: Financial transparency for drivers to understand their
        earning patterns and spending history. Useful for performance analysis.
        """,
        parameters=[
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of transactions to return (default: 20, max: 100)',
                default=20
            ),
            OpenApiParameter(
                name='type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by transaction type',
                enum=['route_completion', 'on_time_performance', 'premium_purchase', 'verification_accuracy']
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Currency transaction history",
                examples=[{
                    "transactions": [
                        {
                            "id": "uuid",
                            "amount": 75,
                            "transaction_type": "route_completion",
                            "description": "Trip completion bonus - Line 12",
                            "balance_after": 1250,
                            "created_at": "2024-02-14T09:30:00Z",
                            "display_amount": "+75 coins",
                            "transaction_type_display": "Route Completion"
                        },
                        {
                            "id": "uuid",
                            "amount": -500,
                            "transaction_type": "premium_purchase",
                            "description": "Purchased Advanced Route Analytics",
                            "balance_after": 1175,
                            "created_at": "2024-02-13T14:15:00Z",
                            "display_amount": "-500 coins",
                            "transaction_type_display": "Premium Purchase"
                        }
                    ]
                }]
            )
        },
        tags=["Driver Virtual Currency"]
    )
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get user's currency transaction history."""
        limit = int(request.query_params.get('limit', 20))
        transaction_type = request.query_params.get('type')
        
        transactions = CurrencyTransaction.objects.filter(
            user=request.user
        ).order_by('-created_at')
        
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        
        transactions = transactions[:limit]
        serializer = DriverCurrencyTransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get Driver Earnings Summary",
        description="""
        **Driver Earnings Analytics Dashboard**
        
        Get comprehensive earnings analytics for the specified time period.
        This endpoint provides insights into earning patterns and performance trends.
        
        **Analytics Included**:
        - **Total Earned**: Sum of all positive transactions in period
        - **Transaction Count**: Number of earning events
        - **Earnings by Type**: Breakdown by activity type
        - **Average Per Day**: Daily earning rate
        - **Trend Analysis**: Performance over time
        
        **Earning Categories Tracked**:
        - Route completion bonuses
        - On-time performance rewards
        - Safety driving incentives
        - Report verification accuracy
        - Achievement unlocks and milestones
        - Consecutive performance streaks
        
        **Use Case**: Performance analytics for drivers to understand their
        earning patterns and identify opportunities for improvement.
        Useful for setting goals and tracking progress over time.
        
        **Business Intelligence**: Helps drivers optimize their performance
        by showing which activities generate the most virtual currency.
        """,
        parameters=[
            OpenApiParameter(
                name='days',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of days to analyze (default: 30, max: 365)',
                default=30
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Comprehensive earnings analytics",
                examples=[{
                    "period_days": 30,
                    "total_earned": 1250,
                    "transaction_count": 18,
                    "average_per_day": 41.67,
                    "by_type": [
                        {
                            "transaction_type": "route_completion",
                            "count": 12,
                            "total_amount": 900
                        },
                        {
                            "transaction_type": "on_time_performance",
                            "count": 4,
                            "total_amount": 200
                        },
                        {
                            "transaction_type": "verification_accuracy",
                            "count": 2,
                            "total_amount": 150
                        }
                    ]
                }]
            )
        },
        tags=["Driver Virtual Currency"]
    )
    @action(detail=False, methods=['get'])
    def earnings_summary(self, request):
        """Get earnings summary for specified period."""
        days = int(request.query_params.get('days', 30))
        summary = DriverCurrencyService.get_driver_earnings_summary(request.user, days)
        return Response(summary)

    @extend_schema(
        summary="Driver Currency Leaderboard",
        description="""
        **Virtual Currency Wealth Leaderboard**
        
        Get the top drivers ranked by virtual currency balance. This leaderboard
        showcases the most successful drivers in the gamification system and
        motivates healthy competition.
        
        **Ranking Methodology**:
        - Primary: Current virtual currency balance
        - Secondary: Lifetime earnings (for ties)
        - Filters: Only active drivers included
        
        **Leaderboard Features**:
        - Real-time rankings
        - Driver performance indicators
        - Balance and lifetime statistics
        - Anonymous or named display options
        
        **Competitive Elements**:
        - Seasonal rankings
        - Monthly competitions
        - Special achievements
        - Top performer recognition
        
        **Privacy**: User names are displayed as provided in profiles.
        Drivers can control their visibility in leaderboards through privacy settings.
        
        **Use Case**: Motivation and gamification element to encourage
        driver engagement and performance improvement through friendly competition.
        """,
        parameters=[
            OpenApiParameter(
                name='period',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Leaderboard period (weekly/monthly/all-time)',
                default='monthly',
                enum=['weekly', 'monthly', 'all-time']
            ),
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of top drivers to return (default: 10, max: 50)',
                default=10
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Driver currency leaderboard",
                examples=[{
                    "period": "monthly",
                    "leaderboard": [
                        {
                            "rank": 1,
                            "user_name": "Ahmed Benaissa",
                            "balance": 2450,
                            "lifetime_earned": 8750
                        },
                        {
                            "rank": 2,
                            "user_name": "Sarah Meziani",
                            "balance": 2180,
                            "lifetime_earned": 7920
                        },
                        {
                            "rank": 3,
                            "user_name": "Karim Ouali",
                            "balance": 1890,
                            "lifetime_earned": 6540
                        }
                    ]
                }]
            )
        },
        tags=["Driver Virtual Currency"]
    )
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get currency leaderboard for drivers."""
        period = request.query_params.get('period', 'monthly')
        limit = int(request.query_params.get('limit', 10))
        
        # Get only drivers in leaderboard
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        currencies = VirtualCurrency.objects.filter(
            user__user_type='driver'
        ).select_related('user').order_by('-balance')[:limit]
        
        leaderboard = []
        for rank, currency in enumerate(currencies, 1):
            leaderboard.append({
                'rank': rank,
                'user_name': currency.user.get_full_name() or currency.user.email,
                'balance': currency.balance,
                'lifetime_earned': currency.lifetime_earned,
            })
        
        return Response({
            'period': period,
            'leaderboard': leaderboard
        })


__all__ = [
    'AnomalyViewSet',
    'BusLineViewSet',
    'BusWaitingListViewSet',
    'DriverCurrencyViewSet',
    'DriverPerformanceScoreViewSet',
    'LocationUpdateViewSet',
    'PassengerCountViewSet',
    'PremiumFeatureViewSet',
    'ReputationScoreViewSet',
    'TripViewSet',
    'UserPremiumFeatureViewSet',
    'VirtualCurrencyViewSet',
    'WaitingCountReportViewSet',
    'WaitingPassengersViewSet',
]