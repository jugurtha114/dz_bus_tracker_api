"""
Active buses view for real-time tracking.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.tracking.models import BusLine
from apps.buses.models import Bus
from apps.api.v1.buses.serializers import BusSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def active_buses(request):
    """
    Get all active buses currently tracking.
    """
    # Get active bus lines
    active_bus_lines = BusLine.objects.filter(
        is_active=True,
        tracking_status='active'
    ).select_related('bus', 'line', 'bus__driver')
    
    # Get the buses
    bus_ids = active_bus_lines.values_list('bus_id', flat=True)
    buses = Bus.objects.filter(id__in=bus_ids).select_related('driver', 'driver__user')
    
    # Add current tracking info to buses
    bus_data = []
    for bus in buses:
        bus_info = BusSerializer(bus, context={'request': request}).data
        
        # Get the bus line info
        bus_line = active_bus_lines.filter(bus=bus).first()
        if bus_line:
            bus_info['current_line'] = {
                'id': str(bus_line.line.id),
                'name': bus_line.line.name,
                'code': bus_line.line.code,
            }
            bus_info['trip_id'] = str(bus_line.trip_id) if bus_line.trip_id else None
            bus_info['tracking_started_at'] = bus_line.start_time
            
            # Get latest location
            try:
                from apps.tracking.models import LocationUpdate
                latest_location = LocationUpdate.objects.filter(
                    bus=bus
                ).order_by('-created_at').first()
                
                if latest_location:
                    bus_info['current_location'] = {
                        'latitude': float(latest_location.latitude),
                        'longitude': float(latest_location.longitude),
                        'speed': float(latest_location.speed) if latest_location.speed else None,
                        'heading': float(latest_location.heading) if latest_location.heading else None,
                        'updated_at': latest_location.created_at,
                        'nearest_stop': {
                            'id': str(latest_location.nearest_stop.id),
                            'name': latest_location.nearest_stop.name,
                        } if latest_location.nearest_stop else None,
                        'distance_to_stop': float(latest_location.distance_to_stop) if latest_location.distance_to_stop else None,
                    }
            except Exception:
                pass
            
            # Get passenger count
            try:
                from apps.tracking.models import PassengerCount
                latest_count = PassengerCount.objects.filter(
                    bus=bus
                ).order_by('-created_at').first()
                
                if latest_count:
                    bus_info['passenger_count'] = {
                        'count': latest_count.count,
                        'capacity': latest_count.capacity,
                        'occupancy_rate': float(latest_count.occupancy_rate),
                        'updated_at': latest_count.created_at,
                    }
            except Exception:
                pass
        
        bus_data.append(bus_info)
    
    return Response({
        'count': len(bus_data),
        'buses': bus_data,
    })