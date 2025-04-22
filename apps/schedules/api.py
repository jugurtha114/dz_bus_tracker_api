from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsAdminOrDriver, IsOwnerOrAdmin
from .models import Schedule, ScheduleException, ScheduledTrip, MaintenanceSchedule
from .serializers import (
    ScheduleSerializer,
    ScheduleCreateSerializer,
    ScheduleExceptionSerializer,
    ScheduleExceptionCreateSerializer,
    ScheduledTripSerializer,
    ScheduledTripCreateSerializer,
    ScheduledTripUpdateSerializer,
    MaintenanceScheduleSerializer,
    MaintenanceScheduleCreateSerializer,
    MaintenanceScheduleUpdateSerializer,
    ScheduleCalendarSerializer
)
from .selectors import (
    get_schedule_by_id,
    get_schedules_for_line,
    get_schedules_for_bus,
    get_schedules_for_driver,
    get_schedule_exceptions,
    get_scheduled_trip_by_id,
    get_scheduled_trips,
    get_active_trips,
    get_upcoming_trips,
    get_delayed_trips,
    get_maintenance_by_id,
    get_maintenance_schedules,
    get_current_maintenance_schedules,
    get_overdue_maintenance_schedules,
    get_buses_due_for_maintenance,
    get_schedule_conflicts,
    get_schedule_stats
)
from .services import (
    create_schedule,
    update_schedule,
    check_schedule_conflict,
    create_schedule_exception,
    generate_trips_for_schedule,
    start_scheduled_trip,
    complete_scheduled_trip,
    cancel_scheduled_trip,
    create_maintenance_schedule,
    update_maintenance_schedule,
    complete_maintenance,
    get_calendar_data,
    get_trip_conflicts
)


class ScheduleViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    select_related_fields = ['line', 'bus', 'driver']
    filterset_fields = ['line', 'bus', 'driver', 'is_peak_hour']
    search_fields = ['line__name', 'bus__matricule']
    permission_classes = [permissions.IsAuthenticated, IsAdminOrDriver]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ScheduleCreateSerializer
        return ScheduleSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            active = active.lower() == 'true'
            queryset = queryset.filter(is_active=active)
        
        # Filter by day of week
        day = self.request.query_params.get('day')
        if day is not None:
            try:
                day = int(day)
                queryset = queryset.filter(days_of_week__contains=[day])
            except (ValueError, TypeError):
                pass
        
        # If user is a driver, only show their schedules
        if self.request.user.is_driver and not self.request.user.is_admin:
            from apps.drivers.selectors import get_driver_for_user
            driver = get_driver_for_user(self.request.user)
            if driver:
                queryset = queryset.filter(driver=driver)
        
        return queryset
    
    def perform_create(self, serializer):
        create_schedule(serializer.validated_data)
    
    def perform_update(self, serializer):
        update_schedule(self.get_object().id, serializer.validated_data)
    
    @action(detail=True, methods=['post'])
    def generate_trips(self, request, pk=None):
        schedule = self.get_object()
        
        # Get parameters
        start_date = request.data.get('start_date')
        date_range = request.data.get('date_range', 7)
        
        try:
            date_range = int(date_range)
        except (ValueError, TypeError):
            date_range = 7
        
        # Generate trips
        trips = generate_trips_for_schedule(
            schedule.id,
            start_date=start_date,
            date_range=date_range
        )
        
        return Response({
            'detail': f'Generated {len(trips)} trips.',
            'count': len(trips)
        })
    
    @action(detail=False, methods=['get'])
    def for_line(self, request):
        line_id = request.query_params.get('line_id')
        
        if not line_id:
            return Response(
                {'detail': 'Line ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        schedules = get_schedules_for_line(line_id)
        
        page = self.paginate_queryset(schedules)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(schedules, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_bus(self, request):
        bus_id = request.query_params.get('bus_id')
        
        if not bus_id:
            return Response(
                {'detail': 'Bus ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        schedules = get_schedules_for_bus(bus_id)
        
        page = self.paginate_queryset(schedules)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(schedules, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_driver(self, request):
        driver_id = request.query_params.get('driver_id')
        
        if not driver_id:
            # If no driver_id provided and user is a driver, use their ID
            if self.request.user.is_driver:
                from apps.drivers.selectors import get_driver_for_user
                driver = get_driver_for_user(self.request.user)
                if driver:
                    driver_id = driver.id
                else:
                    return Response(
                        {'detail': 'Driver profile not found.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                return Response(
                    {'detail': 'Driver ID is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        schedules = get_schedules_for_driver(driver_id)
        
        page = self.paginate_queryset(schedules)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(schedules, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def check_conflicts(self, request):
        serializer = ScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        # Check bus conflicts
        bus_conflict = check_schedule_conflict(
            data['bus'],
            None,
            data['days_of_week'],
            data['start_time'],
            data['end_time']
        )
        
        # Check driver conflicts
        driver_conflict = check_schedule_conflict(
            data['driver'],
            None,
            data['days_of_week'],
            data['start_time'],
            data['end_time']
        )
        
        return Response({
            'has_conflict': bus_conflict or driver_conflict,
            'bus_conflict': bus_conflict,
            'driver_conflict': driver_conflict
        })
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        # Get parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        bus_id = request.query_params.get('bus_id')
        driver_id = request.query_params.get('driver_id')
        line_id = request.query_params.get('line_id')
        
        # Get calendar data
        calendar_data = get_calendar_data(
            start_date=start_date,
            end_date=end_date,
            bus_id=bus_id,
            driver_id=driver_id,
            line_id=line_id
        )
        
        # Serialize data
        serializer = ScheduleCalendarSerializer(calendar_data, many=True)
        return Response(serializer.data)


class ScheduleExceptionViewSet(BaseViewSet):
    queryset = ScheduleException.objects.all()
    serializer_class = ScheduleExceptionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrDriver]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ScheduleExceptionCreateSerializer
        return ScheduleExceptionSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by schedule
        schedule_id = self.request.query_params.get('schedule')
        if schedule_id:
            queryset = queryset.filter(schedule_id=schedule_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # If user is a driver, only show exceptions for their schedules
        if self.request.user.is_driver and not self.request.user.is_admin:
            from apps.drivers.selectors import get_driver_for_user
            driver = get_driver_for_user(self.request.user)
            if driver:
                queryset = queryset.filter(schedule__driver=driver)
        
        return queryset.select_related('schedule')
    
    def perform_create(self, serializer):
        create_schedule_exception(serializer.validated_data)


class ScheduledTripViewSet(BaseViewSet):
    queryset = ScheduledTrip.objects.all()
    serializer_class = ScheduledTripSerializer
    select_related_fields = ['schedule', 'schedule__line', 'schedule__bus', 'schedule__driver', 'tracking_session']
    permission_classes = [permissions.IsAuthenticated, IsAdminOrDriver]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ScheduledTripCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ScheduledTripUpdateSerializer
        return ScheduledTripSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by schedule
        schedule_id = self.request.query_params.get('schedule')
        if schedule_id:
            queryset = queryset.filter(schedule_id=schedule_id)
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(schedule__bus_id=bus_id)
        
        # Filter by driver
        driver_id = self.request.query_params.get('driver')
        if driver_id:
            queryset = queryset.filter(schedule__driver_id=driver_id)
            
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(schedule__line_id=line_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # If user is a driver, only show trips for their schedules
        if self.request.user.is_driver and not self.request.user.is_admin:
            from apps.drivers.selectors import get_driver_for_user
            driver = get_driver_for_user(self.request.user)
            if driver:
                queryset = queryset.filter(schedule__driver=driver)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        trip = self.get_object()
        
        try:
            started_trip = start_scheduled_trip(trip.id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(self.get_serializer(started_trip).data)
    
    @action(detail=True, methods=['post'])
    def complete_trip(self, request, pk=None):
        trip = self.get_object()
        
        try:
            completed_trip = complete_scheduled_trip(trip.id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(self.get_serializer(completed_trip).data)
    
    @action(detail=True, methods=['post'])
    def cancel_trip(self, request, pk=None):
        trip = self.get_object()
        reason = request.data.get('reason', '')
        
        try:
            cancelled_trip = cancel_scheduled_trip(trip.id, reason)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(self.get_serializer(cancelled_trip).data)
    
    @action(detail=True, methods=['get'])
    def conflicts(self, request, pk=None):
        trip = self.get_object()
        
        conflicts = get_trip_conflicts(trip)
        
        # Custom serialization for conflicts
        result = []
        
        for conflict in conflicts:
            conflict_type = conflict['type']
            conflict_obj = conflict['object']
            reason = conflict['reason']
            
            if conflict_type == 'trip':
                serializer = self.get_serializer(conflict_obj)
                data = serializer.data
            elif conflict_type == 'maintenance':
                serializer = MaintenanceScheduleSerializer(conflict_obj)
                data = serializer.data
            else:
                continue
            
            result.append({
                'type': conflict_type,
                'data': data,
                'reason': reason
            })
        
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        trips = get_active_trips()
        
        page = self.paginate_queryset(trips)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(trips, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        limit = request.query_params.get('limit', 10)
        hours_ahead = request.query_params.get('hours', 24)
        
        try:
            limit = int(limit)
            hours_ahead = int(hours_ahead)
        except (ValueError, TypeError):
            limit = 10
            hours_ahead = 24
        
        trips = get_upcoming_trips(limit=limit, hours_ahead=hours_ahead)
        
        serializer = self.get_serializer(trips, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def delayed(self, request):
        trips = get_delayed_trips()
        
        page = self.paginate_queryset(trips)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(trips, many=True)
        return Response(serializer.data)


class MaintenanceScheduleViewSet(BaseViewSet):
    queryset = MaintenanceSchedule.objects.all()
    serializer_class = MaintenanceScheduleSerializer
    select_related_fields = ['bus']
    permission_classes = [permissions.IsAuthenticated, IsAdminOrDriver]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return MaintenanceScheduleCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return MaintenanceScheduleUpdateSerializer
        return MaintenanceScheduleSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by bus
        bus_id = self.request.query_params.get('bus')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(end_date__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)
        
        # Filter by type
        maintenance_type = self.request.query_params.get('type')
        if maintenance_type:
            queryset = queryset.filter(maintenance_type=maintenance_type)
        
        # Filter by completion status
        completed = self.request.query_params.get('completed')
        if completed is not None:
            completed = completed.lower() == 'true'
            queryset = queryset.filter(is_completed=completed)
        
        # If user is a driver, only show maintenance for their buses
        if self.request.user.is_driver and not self.request.user.is_admin:
            from apps.drivers.selectors import get_driver_for_user
            driver = get_driver_for_user(self.request.user)
            if driver:
                queryset = queryset.filter(bus__driver=driver)
        
        return queryset
    
    def perform_create(self, serializer):
        create_maintenance_schedule(serializer.validated_data)
    
    def perform_update(self, serializer):
        update_maintenance_schedule(self.get_object().id, serializer.validated_data)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        maintenance = self.get_object()
        
        try:
            completed_maintenance = complete_maintenance(maintenance.id)
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(self.get_serializer(completed_maintenance).data)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        maintenance_schedules = get_current_maintenance_schedules()
        
        page = self.paginate_queryset(maintenance_schedules)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(maintenance_schedules, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def overdue(self, request):
        maintenance_schedules = get_overdue_maintenance_schedules()
        
        page = self.paginate_queryset(maintenance_schedules)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(maintenance_schedules, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def buses_due(self, request):
        days_ahead = request.query_params.get('days', 30)
        
        try:
            days_ahead = int(days_ahead)
        except (ValueError, TypeError):
            days_ahead = 30
        
        buses = get_buses_due_for_maintenance(days_ahead=days_ahead)
        
        from apps.buses.serializers import BusSerializer
        serializer = BusSerializer(buses, many=True)
        return Response(serializer.data)

    # from rest_framework import status, permissions
    # from rest_framework.decorators import action
    # from rest_framework.response import Response
    #
    # from apps.core.base.api import BaseViewSet
    # from apps.core.base.permissions import IsAdmin, IsOwnerOrAdmin
    # from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest
    # from .serializers import (
    #     PassengerSerializer,
    #     PassengerUpdateSerializer,
    #     SavedLocationSerializer,
    #     SavedLocationCreateSerializer,
    #     TripHistorySerializer,
    #     TripHistoryCreateSerializer,
    #     TripHistoryUpdateSerializer,
    #     FeedbackRequestSerializer,
    #     NotificationPreferencesSerializer,
    #     PassengerStatsSerializer
    # )
    # from .selectors import (
    #     get_passenger_by_id,
    #     get_passenger_for_user,
    #     get_saved_locations,
    #     get_saved_location_by_id,
    #     get_nearest_saved_location,
    #     get_trip_history,
    #     get_trip_by_id,
    #     get_active_trips,
    #     get_recent_trips,
    #     get_feedback_requests,
    #     get_pending_feedback_requests
    # )
    # from .services import (
    #     create_passenger,
    #     update_passenger,
    #     update_notification_preferences,
    #     add_saved_location,
    #     update_saved_location,
    #     delete_saved_location,
    #     start_trip,
    #     complete_trip,
    #     cancel_trip,
    #     create_feedback_request,
    #     complete_feedback_request,
    #     get_passenger_stats
    # )
    #
    # class PassengerViewSet(BaseViewSet):
    #     queryset = Passenger.objects.all()
    #     serializer_class = PassengerSerializer
    #
    #     def get_permissions(self):
    #         if self.action in ['create', 'update', 'partial_update', 'destroy']:
    #             return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    #         return [permissions.IsAuthenticated()]
    #
    #     def get_serializer_class(self):
    #         if self.action in ['update', 'partial_update']:
    #             return PassengerUpdateSerializer
    #         elif self.action == 'stats':
    #             return PassengerStatsSerializer
    #         elif self.action == 'notification_preferences':
    #             return NotificationPreferencesSerializer
    #         return PassengerSerializer
    #
    #     def get_queryset(self):
    #         # Only return profile for the current user unless admin
    #         if self.request.user.is_admin:
    #             return self.queryset
    #
    #         return self.queryset.filter(user=self.request.user)
    #
    #     def perform_create(self, serializer):
    #         create_passenger(self.request.user)
    #
    #     def perform_update(self, serializer):
    #         update_passenger(
    #             passenger_id=self.get_object().id,
    #             data=serializer.validated_data
    #         )
    #
    #     @action(detail=False, methods=['get'])
    #     def me(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #
    #         if not passenger:
    #             # Create passenger profile if doesn't exist
    #             passenger = create_passenger(request.user)
    #
    #         serializer = self.get_serializer(passenger)
    #         return Response(serializer.data)
    #
    #     @action(detail=True, methods=['get'])
    #     def stats(self, request, pk=None):
    #         passenger = self.get_object()
    #
    #         # Check if user is allowed to view stats
    #         if passenger.user != request.user and not request.user.is_admin:
    #             return Response(
    #                 {'detail': 'You do not have permission to view these stats.'},
    #                 status=status.HTTP_403_FORBIDDEN
    #             )
    #
    #         stats = get_passenger_stats(passenger.id)
    #
    #         serializer = self.get_serializer(data=stats)
    #         serializer.is_valid()  # Already formatted correctly, no need to raise_exception
    #
    #         return Response(serializer.data)
    #
    #     @action(detail=True, methods=['put', 'patch'])
    #     def notification_preferences(self, request, pk=None):
    #         passenger = self.get_object()
    #
    #         # Check if user is allowed to update preferences
    #         if passenger.user != request.user and not request.user.is_admin:
    #             return Response(
    #                 {'detail': 'You do not have permission to update these preferences.'},
    #                 status=status.HTTP_403_FORBIDDEN
    #             )
    #
    #         serializer = NotificationPreferencesSerializer(data=request.data)
    #         serializer.is_valid(raise_exception=True)
    #
    #         updated_passenger = update_notification_preferences(
    #             passenger_id=passenger.id,
    #             preferences=serializer.validated_data
    #         )
    #
    #         return Response(PassengerSerializer(updated_passenger).data)
    #
    # class SavedLocationViewSet(BaseViewSet):
    #     queryset = SavedLocation.objects.all()
    #     serializer_class = SavedLocationSerializer
    #
    #     def get_permissions(self):
    #         return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    #
    #     def get_serializer_class(self):
    #         if self.action == 'create':
    #             return SavedLocationCreateSerializer
    #         return SavedLocationSerializer
    #
    #     def get_queryset(self):
    #         # Only return locations for the current user unless admin
    #         if self.request.user.is_admin:
    #             return self.queryset
    #
    #         passenger = get_passenger_for_user(self.request.user)
    #         if not passenger:
    #             return SavedLocation.objects.none()
    #
    #         return self.queryset.filter(passenger=passenger)
    #
    #     def perform_create(self, serializer):
    #         passenger = get_passenger_for_user(self.request.user)
    #         if not passenger:
    #             passenger = create_passenger(self.request.user)
    #
    #         add_saved_location(
    #             passenger_id=passenger.id,
    #             location_data=serializer.validated_data
    #         )
    #
    #     def perform_update(self, serializer):
    #         update_saved_location(
    #             location_id=self.get_object().id,
    #             data=serializer.validated_data
    #         )
    #
    #     def perform_destroy(self, instance):
    #         delete_saved_location(instance.id)
    #
    #     @action(detail=False, methods=['get'])
    #     def my_locations(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         is_favorite = request.query_params.get('is_favorite')
    #         if is_favorite is not None:
    #             is_favorite = is_favorite.lower() == 'true'
    #
    #         locations = get_saved_locations(passenger.id, is_favorite=is_favorite)
    #
    #         serializer = self.get_serializer(locations, many=True)
    #         return Response(serializer.data)
    #
    #     @action(detail=False, methods=['get'])
    #     def nearest(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response(
    #                 {'detail': 'Passenger profile not found.'},
    #                 status=status.HTTP_404_NOT_FOUND
    #             )
    #
    #         latitude = request.query_params.get('latitude')
    #         longitude = request.query_params.get('longitude')
    #
    #         if not latitude or not longitude:
    #             return Response(
    #                 {'detail': 'Latitude and longitude are required.'},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #
    #         try:
    #             latitude = float(latitude)
    #             longitude = float(longitude)
    #         except ValueError:
    #             return Response(
    #                 {'detail': 'Invalid latitude or longitude.'},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #
    #         max_distance = request.query_params.get('max_distance', 1000)
    #         try:
    #             max_distance = float(max_distance)
    #         except ValueError:
    #             max_distance = 1000
    #
    #         location, distance = get_nearest_saved_location(
    #             passenger_id=passenger.id,
    #             latitude=latitude,
    #             longitude=longitude,
    #             max_distance=max_distance
    #         )
    #
    #         if not location:
    #             return Response(
    #                 {'detail': 'No saved locations found within the specified distance.'},
    #                 status=status.HTTP_404_NOT_FOUND
    #             )
    #
    #         serializer = self.get_serializer(location)
    #         data = serializer.data
    #         data['distance'] = distance
    #
    #         return Response(data)
    #
    # class TripHistoryViewSet(BaseViewSet):
    #     queryset = TripHistory.objects.all()
    #     serializer_class = TripHistorySerializer
    #
    #     def get_permissions(self):
    #         return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    #
    #     def get_serializer_class(self):
    #         if self.action == 'create':
    #             return TripHistoryCreateSerializer
    #         elif self.action in ['update', 'partial_update', 'complete', 'cancel']:
    #             return TripHistoryUpdateSerializer
    #         return TripHistorySerializer
    #
    #     def get_queryset(self):
    #         # Only return trips for the current user unless admin
    #         if self.request.user.is_admin:
    #             return self.queryset
    #
    #         passenger = get_passenger_for_user(self.request.user)
    #         if not passenger:
    #             return TripHistory.objects.none()
    #
    #         return self.queryset.filter(passenger=passenger)
    #
    #     def perform_create(self, serializer):
    #         passenger = get_passenger_for_user(self.request.user)
    #         if not passenger:
    #             passenger = create_passenger(self.request.user)
    #
    #         start_trip(
    #             passenger_id=passenger.id,
    #             line_id=serializer.validated_data['line'].id,
    #             start_stop_id=serializer.validated_data['start_stop'].id,
    #             end_stop_id=serializer.validated_data.get('end_stop')
    #         )
    #
    #     @action(detail=True, methods=['post'])
    #     def complete(self, request, pk=None):
    #         trip = self.get_object()
    #
    #         # Check if user is allowed to complete this trip
    #         if trip.passenger.user != request.user and not request.user.is_admin:
    #             return Response(
    #                 {'detail': 'You do not have permission to complete this trip.'},
    #                 status=status.HTTP_403_FORBIDDEN
    #             )
    #
    #         # Check if trip can be completed
    #         if trip.status != 'started':
    #             return Response(
    #                 {'detail': 'Only active trips can be completed.'},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #
    #         end_stop_id = request.data.get('end_stop_id')
    #
    #         completed_trip = complete_trip(trip.id, end_stop_id)
    #
    #         return Response(TripHistorySerializer(completed_trip).data)
    #
    #     @action(detail=True, methods=['post'])
    #     def cancel(self, request, pk=None):
    #         trip = self.get_object()
    #
    #         # Check if user is allowed to cancel this trip
    #         if trip.passenger.user != request.user and not request.user.is_admin:
    #             return Response(
    #                 {'detail': 'You do not have permission to cancel this trip.'},
    #                 status=status.HTTP_403_FORBIDDEN
    #             )
    #
    #         # Check if trip can be cancelled
    #         if trip.status != 'started':
    #             return Response(
    #                 {'detail': 'Only active trips can be cancelled.'},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #
    #         cancelled_trip = cancel_trip(trip.id)
    #
    #         return Response(TripHistorySerializer(cancelled_trip).data)
    #
    #     @action(detail=False, methods=['get'])
    #     def my_trips(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         status_param = request.query_params.get('status')
    #         limit = request.query_params.get('limit')
    #
    #         if limit:
    #             try:
    #                 limit = int(limit)
    #             except ValueError:
    #                 limit = None
    #
    #         trips = get_trip_history(
    #             passenger_id=passenger.id,
    #             status=status_param,
    #             limit=limit
    #         )
    #
    #         page = self.paginate_queryset(trips)
    #         if page is not None:
    #             serializer = self.get_serializer(page, many=True)
    #             return self.get_paginated_response(serializer.data)
    #
    #         serializer = self.get_serializer(trips, many=True)
    #         return Response(serializer.data)
    #
    #     @action(detail=False, methods=['get'])
    #     def active(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         trips = get_active_trips(passenger.id)
    #
    #         serializer = self.get_serializer(trips, many=True)
    #         return Response(serializer.data)
    #
    #     @action(detail=False, methods=['get'])
    #     def recent(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         days = request.query_params.get('days', 7)
    #         limit = request.query_params.get('limit', 5)
    #
    #         try:
    #             days = int(days)
    #             limit = int(limit)
    #         except ValueError:
    #             days = 7
    #             limit = 5
    #
    #         trips = get_recent_trips(
    #             passenger_id=passenger.id,
    #             days=days,
    #             limit=limit
    #         )
    #
    #         serializer = self.get_serializer(trips, many=True)
    #         return Response(serializer.data)
    #
    # class FeedbackRequestViewSet(BaseViewSet):
    #     queryset = FeedbackRequest.objects.all()
    #     serializer_class = FeedbackRequestSerializer
    #
    #     def get_permissions(self):
    #         if self.action in ['create', 'destroy']:
    #             return [permissions.IsAuthenticated(), IsAdmin()]
    #         return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
    #
    #     def get_queryset(self):
    #         # Only return feedback requests for the current user unless admin
    #         if self.request.user.is_admin:
    #             return self.queryset
    #
    #         passenger = get_passenger_for_user(self.request.user)
    #         if not passenger:
    #             return FeedbackRequest.objects.none()
    #
    #         return self.queryset.filter(passenger=passenger)
    #
    #     def perform_create(self, serializer):
    #         create_feedback_request(
    #             passenger_id=serializer.validated_data['passenger'].id,
    #             line_id=serializer.validated_data['line'].id,
    #             trip_id=serializer.validated_data.get('trip')
    #         )
    #
    #     @action(detail=True, methods=['post'])
    #     def complete(self, request, pk=None):
    #         feedback_request = self.get_object()
    #
    #         # Check if user is allowed to complete this feedback request
    #         if feedback_request.passenger.user != request.user and not request.user.is_admin:
    #             return Response(
    #                 {'detail': 'You do not have permission to complete this feedback request.'},
    #                 status=status.HTTP_403_FORBIDDEN
    #             )
    #
    #         # Check if feedback request is already completed
    #         if feedback_request.is_completed:
    #             return Response(
    #                 {'detail': 'This feedback request is already completed.'},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #
    #         completed_request = complete_feedback_request(feedback_request.id)
    #
    #         return Response(FeedbackRequestSerializer(completed_request).data)
    #
    #     @action(detail=False, methods=['get'])
    #     def my_requests(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         is_completed = request.query_params.get('is_completed')
    #         is_expired = request.query_params.get('is_expired')
    #
    #         if is_completed is not None:
    #             is_completed = is_completed.lower() == 'true'
    #
    #         if is_expired is not None:
    #             is_expired = is_expired.lower() == 'true'
    #
    #         requests = get_feedback_requests(
    #             passenger_id=passenger.id,
    #             is_completed=is_completed,
    #             is_expired=is_expired
    #         )
    #
    #         serializer = self.get_serializer(requests, many=True)
    #         return Response(serializer.data)
    #
    #     @action(detail=False, methods=['get'])
    #     def pending(self, request):
    #         passenger = get_passenger_for_user(request.user)
    #         if not passenger:
    #             return Response([])
    #
    #         requests = get_pending_feedback_requests(passenger.id)
    #
    #         serializer = self.get_serializer(requests, many=True)
    #         return Response(serializer.data)