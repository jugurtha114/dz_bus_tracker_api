"""
Views for the buses API.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.viewsets import BaseModelViewSet
from apps.buses.models import Bus
from apps.buses.services import BusService
from apps.core.permissions import IsAdmin, IsApprovedDriver, IsDriverOrAdmin

from .filters import BusFilter
from .serializers import (
    BusApproveSerializer,
    BusCreateSerializer,
    BusSerializer,
    BusUpdateSerializer,
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
        if self.action in ['update_location', 'stop_tracking']:
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
    def stop_tracking(self, request, pk=None):
        """
        Stop tracking a bus (marks it as no longer actively tracked).
        Bus location tracking is managed via the tracking app's update_location endpoint.
        """
        bus = self.get_object()

        # Ensure the driver is the owner of this bus
        if bus.driver.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to stop tracking this bus'},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({'detail': 'Tracking stopped'})
