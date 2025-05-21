"""
Views for the buses API.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet, ReadOnlyModelViewSet
from apps.buses.models import Bus, BusLocation
from apps.buses.services import BusService, BusLocationService
from apps.core.permissions import IsAdmin, IsApprovedDriver, IsDriverOrAdmin

from .filters import BusFilter, BusLocationFilter
from .serializers import (
    BusApproveSerializer,
    BusCreateSerializer,
    BusLocationCreateSerializer,
    BusLocationSerializer,
    BusLocationUpdateSerializer,
    BusSerializer,
    BusUpdateSerializer,
    PassengerCountUpdateSerializer,
)


class BusViewSet(BaseModelViewSet):
    """
    API endpoint for buses.
    """
    queryset = Bus.objects.all()
    serializer_class = BusSerializer
    filterset_class = BusFilter
    service_class = BusService

    def get_queryset(self):
        """
        Filter buses based on user type.
        """
        queryset = super().get_queryset()

        # Drivers can only see their own buses
        user = self.request.user
        if user.is_driver and not user.is_staff:
            return queryset.filter(driver__user=user)

        return queryset

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsDriverOrAdmin()]
        if self.action in ['approve', 'activate', 'deactivate']:
            return [IsAdmin()]
        if self.action in ['update_location', 'update_passenger_count', 'start_tracking', 'stop_tracking']:
            return [IsApprovedDriver()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return BusCreateSerializer
        if self.action in ['update', 'partial_update']:
            return BusUpdateSerializer
        if self.action == 'approve':
            return BusApproveSerializer
        if self.action == 'update_location':
            return BusLocationUpdateSerializer
        if self.action == 'update_passenger_count':
            return PassengerCountUpdateSerializer
        return BusSerializer

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve or reject a bus.
        """
        bus = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data['approve']:
            BusService.approve_bus(bus.id)
            return Response({'detail': 'Bus approved'})
        else:
            BusService.unapprove_bus(bus.id)
            return Response({'detail': 'Bus rejected'})

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate a bus.
        """
        bus = self.get_object()
        BusService.activate_bus(bus.id)
        return Response({'detail': 'Bus activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate a bus.
        """
        bus = self.get_object()
        BusService.deactivate_bus(bus.id)
        return Response({'detail': 'Bus deactivated'})

    @action(detail=True, methods=['post'])
    def update_location(self, request, pk=None):
        """
        Update bus location.
        """
        bus = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Ensure the driver is the owner of this bus
        if bus.driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to update this bus location'},
                status=status.HTTP_403_FORBIDDEN
            )

        location = BusLocationService.update_location(
            bus_id=bus.id,
            **serializer.validated_data
        )

        response_serializer = BusLocationSerializer(location)
        return Response(response_serializer.data)

    @action(detail=True, methods=['post'])
    def update_passenger_count(self, request, pk=None):
        """
        Update passenger count.
        """
        bus = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Ensure the driver is the owner of this bus
        if bus.driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to update this bus passenger count'},
                status=status.HTTP_403_FORBIDDEN
            )

        location = BusLocationService.update_passenger_count(
            bus_id=bus.id,
            passenger_count=serializer.validated_data['count']
        )

        response_serializer = BusLocationSerializer(location)
        return Response(response_serializer.data)

    @action(detail=True, methods=['post'])
    def start_tracking(self, request, pk=None):
        """
        Start tracking a bus.
        """
        bus = self.get_object()

        # Ensure the driver is the owner of this bus
        if bus.driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to track this bus'},
                status=status.HTTP_403_FORBIDDEN
            )

        location = BusLocationService.start_tracking(bus.id)

        if location:
            response_serializer = BusLocationSerializer(location)
            return Response(response_serializer.data)

        return Response({'detail': 'Tracking started'})

    @action(detail=True, methods=['post'])
    def stop_tracking(self, request, pk=None):
        """
        Stop tracking a bus.
        """
        bus = self.get_object()

        # Ensure the driver is the owner of this bus
        if bus.driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to stop tracking this bus'},
                status=status.HTTP_403_FORBIDDEN
            )

        location = BusLocationService.stop_tracking(bus.id)

        if location:
            response_serializer = BusLocationSerializer(location)
            return Response(response_serializer.data)

        return Response({'detail': 'Tracking stopped'})


class BusLocationViewSet(ReadOnlyModelViewSet):
    """
    API endpoint for bus locations.
    """
    queryset = BusLocation.objects.all()
    serializer_class = BusLocationSerializer
    filterset_class = BusLocationFilter

    def get_queryset(self):
        """
        Filter locations based on user type and parameters.
        """
        queryset = super().get_queryset()

        # Filter by bus if provided
        bus_id = self.request.query_params.get('bus_id')
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)

        # Limit history if requested
        limit = self.request.query_params.get('limit')
        if limit and limit.isdigit():
            queryset = queryset.order_by('-created_at')[:int(limit)]
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        return [IsAuthenticated()]