from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.base.api import BaseViewSet, OptimizedFilterMixin
from apps.core.base.permissions import IsAdmin, IsOwnerOrAdmin
from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest
from .serializers import (
    PassengerSerializer,
    PassengerUpdateSerializer,
    SavedLocationSerializer,
    SavedLocationCreateSerializer,
    TripHistorySerializer,
    TripHistoryCreateSerializer,
    TripHistoryUpdateSerializer,
    FeedbackRequestSerializer,
    NotificationPreferencesSerializer,
    PassengerStatsSerializer
)
from .selectors import (
    get_passenger_by_id,
    get_passenger_for_user,
    get_saved_locations,
    get_saved_location_by_id,
    get_nearest_saved_location,
    get_trip_history,
    get_trip_by_id,
    get_active_trips,
    get_recent_trips,
    get_feedback_requests,
    get_feedback_request_by_id,
    get_pending_feedback_requests
)
from .services import (
    create_passenger,
    update_passenger,
    update_notification_preferences,
    add_saved_location,
    update_saved_location,
    delete_saved_location,
    start_trip,
    complete_trip,
    cancel_trip,
    create_feedback_request,
    complete_feedback_request,
    get_passenger_stats
)


class PassengerViewSet(OptimizedFilterMixin, BaseViewSet):
    queryset = Passenger.objects.all()
    serializer_class = PassengerSerializer
    select_related_fields = ['user']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return PassengerUpdateSerializer
        elif self.action == 'notification_preferences':
            return NotificationPreferencesSerializer
        elif self.action == 'stats':
            return PassengerStatsSerializer
        return PassengerSerializer
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'saved_locations', 'trips', 'notification_preferences', 'stats']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            active = active.lower() == 'true'
            queryset = queryset.filter(is_active=active)
        
        # If user is not an admin, only show their own profile
        if not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        create_passenger(serializer.validated_data['user'])
    
    def perform_update(self, serializer):
        update_passenger(
            passenger_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        passenger = get_passenger_for_user(request.user)
        
        if not passenger:
            # Create passenger profile if it doesn't exist
            passenger = create_passenger(request.user)
        
        serializer = self.get_serializer(passenger)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get', 'put', 'patch'])
    def notification_preferences(self, request, pk=None):
        passenger = self.get_object()
        
        if request.method == 'GET':
            preferences = passenger.notification_preferences or {}
            serializer = self.get_serializer(data=preferences)
            serializer.is_valid()  # No need to raise exception as we're validating known data
            return Response(serializer.data)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        updated_passenger = update_notification_preferences(
            passenger_id=passenger.id,
            preferences=serializer.validated_data
        )
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def saved_locations(self, request, pk=None):
        passenger = self.get_object()
        
        is_favorite = request.query_params.get('favorite')
        if is_favorite:
            is_favorite = is_favorite.lower() == 'true'
        else:
            is_favorite = None
        
        locations = get_saved_locations(passenger.id, is_favorite=is_favorite)
        
        serializer = SavedLocationSerializer(locations, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def trips(self, request, pk=None):
        passenger = self.get_object()
        
        status_param = request.query_params.get('status')
        limit = request.query_params.get('limit')
        
        if limit:
            try:
                limit = int(limit)
            except ValueError:
                limit = None
        
        trips = get_trip_history(passenger.id, status=status_param, limit=limit)
        
        serializer = TripHistorySerializer(trips, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def active_trips(self, request, pk=None):
        passenger = self.get_object()
        
        trips = get_active_trips(passenger.id)
        
        serializer = TripHistorySerializer(trips, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def recent_trips(self, request, pk=None):
        passenger = self.get_object()
        
        days = request.query_params.get('days', 7)
        limit = request.query_params.get('limit', 5)
        
        try:
            days = int(days)
            limit = int(limit)
        except ValueError:
            days = 7
            limit = 5
        
        trips = get_recent_trips(passenger.id, days=days, limit=limit)
        
        serializer = TripHistorySerializer(trips, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def feedback_requests(self, request, pk=None):
        passenger = self.get_object()
        
        is_completed = request.query_params.get('completed')
        if is_completed:
            is_completed = is_completed.lower() == 'true'
        else:
            is_completed = None
        
        is_expired = request.query_params.get('expired')
        if is_expired:
            is_expired = is_expired.lower() == 'true'
        else:
            is_expired = None
        
        requests = get_feedback_requests(
            passenger.id,
            is_completed=is_completed,
            is_expired=is_expired
        )
        
        serializer = FeedbackRequestSerializer(requests, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def pending_feedback(self, request, pk=None):
        passenger = self.get_object()
        
        requests = get_pending_feedback_requests(passenger.id)
        
        serializer = FeedbackRequestSerializer(requests, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        passenger = self.get_object()
        
        stats = get_passenger_stats(passenger.id)
        
        serializer = self.get_serializer(data=stats)
        serializer.is_valid()  # No need to raise exception as we're validating known data
        
        return Response(serializer.data)


class SavedLocationViewSet(BaseViewSet):
    queryset = SavedLocation.objects.all()
    serializer_class = SavedLocationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SavedLocationCreateSerializer
        return SavedLocationSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by passenger
        passenger_id = self.request.query_params.get('passenger')
        if passenger_id:
            queryset = queryset.filter(passenger_id=passenger_id)
        
        # Filter by favorite status
        is_favorite = self.request.query_params.get('favorite')
        if is_favorite:
            is_favorite = is_favorite.lower() == 'true'
            queryset = queryset.filter(is_favorite=is_favorite)
        
        # If user is not an admin, only show their own locations
        if not self.request.user.is_admin:
            queryset = queryset.filter(passenger__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        passenger = get_passenger_for_user(self.request.user)
        
        if not passenger:
            passenger = create_passenger(self.request.user)
        
        add_saved_location(
            passenger_id=passenger.id,
            location_data=serializer.validated_data
        )
    
    def perform_update(self, serializer):
        update_saved_location(
            location_id=self.get_object().id,
            data=serializer.validated_data
        )
    
    def perform_destroy(self, instance):
        delete_saved_location(instance.id)
    
    @action(detail=False, methods=['get'])
    def nearest(self, request):
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        max_distance = request.query_params.get('max_distance', 1000)
        
        if not latitude or not longitude:
            return Response(
                {'detail': 'Latitude and longitude are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            max_distance = float(max_distance)
        except ValueError:
            max_distance = 1000
        
        passenger = get_passenger_for_user(request.user)
        
        if not passenger:
            return Response(
                {'detail': 'Passenger profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        location, distance = get_nearest_saved_location(
            passenger.id,
            latitude,
            longitude,
            max_distance=max_distance
        )
        
        if not location:
            return Response(
                {'detail': 'No saved locations found within the specified distance.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(location)
        data = serializer.data
        data['distance'] = distance
        
        return Response(data)


class TripHistoryViewSet(BaseViewSet):
    queryset = TripHistory.objects.all()
    serializer_class = TripHistorySerializer
    select_related_fields = ['passenger', 'passenger__user', 'line', 'start_stop', 'end_stop']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TripHistoryCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TripHistoryUpdateSerializer
        return TripHistorySerializer
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'complete', 'cancel']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by passenger
        passenger_id = self.request.query_params.get('passenger')
        if passenger_id:
            queryset = queryset.filter(passenger_id=passenger_id)
        
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by time range
        start_time = self.request.query_params.get('start_time')
        if start_time:
            queryset = queryset.filter(start_time__gte=start_time)
        
        end_time = self.request.query_params.get('end_time')
        if end_time:
            queryset = queryset.filter(start_time__lte=end_time)
        
        # If user is not an admin, only show their own trips
        if not self.request.user.is_admin:
            queryset = queryset.filter(passenger__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        passenger = get_passenger_for_user(self.request.user)
        
        if not passenger:
            passenger = create_passenger(self.request.user)
        
        start_trip(
            passenger_id=passenger.id,
            line_id=serializer.validated_data['line'].id,
            start_stop_id=serializer.validated_data['start_stop'].id,
            end_stop_id=serializer.validated_data.get('end_stop', {}).id if serializer.validated_data.get('end_stop') else None
        )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        trip = self.get_object()
        
        end_stop_id = request.data.get('end_stop_id')
        
        completed_trip = complete_trip(
            trip_id=trip.id,
            end_stop_id=end_stop_id
        )
        
        serializer = self.get_serializer(completed_trip)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        trip = self.get_object()
        
        cancelled_trip = cancel_trip(trip.id)
        
        serializer = self.get_serializer(cancelled_trip)
        return Response(serializer.data)


class FeedbackRequestViewSet(BaseViewSet):
    queryset = FeedbackRequest.objects.all()
    serializer_class = FeedbackRequestSerializer
    select_related_fields = ['passenger', 'passenger__user', 'line', 'trip']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by passenger
        passenger_id = self.request.query_params.get('passenger')
        if passenger_id:
            queryset = queryset.filter(passenger_id=passenger_id)
        
        # Filter by line
        line_id = self.request.query_params.get('line')
        if line_id:
            queryset = queryset.filter(line_id=line_id)
        
        # Filter by completion status
        is_completed = self.request.query_params.get('completed')
        if is_completed:
            is_completed = is_completed.lower() == 'true'
            queryset = queryset.filter(is_completed=is_completed)
        
        # If user is not an admin, only show their own feedback requests
        if not self.request.user.is_admin:
            queryset = queryset.filter(passenger__user=self.request.user)
        
        return queryset
    
    def perform_create(self, serializer):
        passenger = get_passenger_for_user(self.request.user)
        
        if not passenger:
            passenger = create_passenger(self.request.user)
        
        create_feedback_request(
            passenger_id=passenger.id,
            line_id=serializer.validated_data['line'].id,
            trip_id=serializer.validated_data.get('trip', {}).id if serializer.validated_data.get('trip') else None
        )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        feedback_request = self.get_object()
        
        completed_request = complete_feedback_request(feedback_request.id)
        
        serializer = self.get_serializer(completed_request)
        return Response(serializer.data)
