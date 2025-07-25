"""
Views for enhanced route tracking and visualization.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.api.viewsets import BaseModelViewSet
from apps.tracking.services.route_service import RouteService
from apps.tracking.models import RouteSegment
from ..serializers.route_serializers import (
    BusRouteSerializer,
    BusArrivalEstimateSerializer,
    RouteVisualizationSerializer,
    RouteSegmentSerializer,
    EstimateArrivalRequestSerializer,
)


class RouteTrackingViewSet(viewsets.ViewSet):
    """
    ViewSet for enhanced route tracking features.
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="Get estimated route for a bus",
        description="Get the estimated route, remaining stops, and ETA for a specific bus",
        parameters=[
            OpenApiParameter(
                name='bus_id',
                description='Bus ID',
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name='destination_stop_id',
                description='Optional destination stop ID',
                required=False,
                type=str,
            ),
        ],
        responses={200: BusRouteSerializer}
    )
    @action(detail=False, methods=['get'])
    def bus_route(self, request):
        """Get estimated route for a bus."""
        bus_id = request.query_params.get('bus_id')
        if not bus_id:
            return Response(
                {'detail': 'bus_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        destination_stop_id = request.query_params.get('destination_stop_id')
        
        try:
            route_data = RouteService.get_estimated_route(
                bus_id=bus_id,
                destination_stop_id=destination_stop_id
            )
            
            serializer = BusRouteSerializer(route_data)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        summary="Get arrival estimates for a stop",
        description="Get estimated arrival times for all buses approaching a specific stop",
        parameters=[
            OpenApiParameter(
                name='stop_id',
                description='Stop ID',
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name='line_id',
                description='Optional line ID to filter by',
                required=False,
                type=str,
            ),
        ],
        responses={200: BusArrivalEstimateSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def arrivals(self, request):
        """Get arrival estimates for a stop."""
        stop_id = request.query_params.get('stop_id')
        if not stop_id:
            return Response(
                {'detail': 'stop_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        line_id = request.query_params.get('line_id')
        
        try:
            estimates = RouteService.get_arrival_estimates(
                stop_id=stop_id,
                line_id=line_id
            )
            
            serializer = BusArrivalEstimateSerializer(estimates, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        summary="Get route visualization data",
        description="Get route data optimized for map visualization including polylines and markers",
        parameters=[
            OpenApiParameter(
                name='line_id',
                description='Line ID',
                required=True,
                type=str,
            ),
        ],
        responses={200: RouteVisualizationSerializer}
    )
    @action(detail=False, methods=['get'])
    def visualization(self, request):
        """Get route visualization data."""
        line_id = request.query_params.get('line_id')
        if not line_id:
            return Response(
                {'detail': 'line_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            visualization_data = RouteService.get_route_visualization_data(line_id)
            
            serializer = RouteVisualizationSerializer(visualization_data)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        summary="Track driver in real-time",
        description="Get real-time tracking data for the current driver",
        responses={200: BusRouteSerializer}
    )
    @action(detail=False, methods=['get'])
    def track_me(self, request):
        """Track current driver's bus."""
        # Check if user is a driver
        if not hasattr(request.user, 'driver'):
            return Response(
                {'detail': 'This endpoint is only available for drivers'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        driver = request.user.driver
        
        # Get driver's active bus
        from apps.buses.models import Bus
        bus = Bus.objects.filter(
            driver=driver,
            status='active'
        ).first()
        
        if not bus:
            return Response(
                {'detail': 'No active bus found for this driver'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            route_data = RouteService.get_estimated_route(bus_id=str(bus.id))
            
            serializer = BusRouteSerializer(route_data)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class RouteSegmentViewSet(BaseModelViewSet):
    """
    ViewSet for managing route segments.
    """
    queryset = RouteSegment.objects.all()
    serializer_class = RouteSegmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter route segments."""
        queryset = super().get_queryset()
        
        from_stop = self.request.query_params.get('from_stop')
        if from_stop:
            queryset = queryset.filter(from_stop_id=from_stop)
        
        to_stop = self.request.query_params.get('to_stop')
        if to_stop:
            queryset = queryset.filter(to_stop_id=to_stop)
        
        return queryset