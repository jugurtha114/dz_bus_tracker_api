"""
Selector functions for the lines app.
"""
from django.db.models import Count, F, Q
import logging

from apps.core.selectors import get_object_or_404
from apps.core.utils.geo import calculate_distance

from .models import Line, LineStop, Schedule, Stop

logger = logging.getLogger(__name__)


def get_line_by_id(line_id):
    """
    Get a line by ID.

    Args:
        line_id: ID of the line

    Returns:
        Line object
    """
    return get_object_or_404(Line, id=line_id)


def get_line_by_code(code):
    """
    Get a line by code.

    Args:
        code: Code of the line

    Returns:
        Line object
    """
    return get_object_or_404(Line, code=code)


def get_stop_by_id(stop_id):
    """
    Get a stop by ID.

    Args:
        stop_id: ID of the stop

    Returns:
        Stop object
    """
    return get_object_or_404(Stop, id=stop_id)


def get_stops_by_line(line_id):
    """
    Get stops for a line in order.

    Args:
        line_id: ID of the line

    Returns:
        Queryset of stops
    """
    line_stops = LineStop.objects.filter(line_id=line_id).order_by('order')
    return Stop.objects.filter(id__in=line_stops.values_list('stop_id', flat=True))


def get_line_stop(line_id, stop_id):
    """
    Get a line-stop relationship.

    Args:
        line_id: ID of the line
        stop_id: ID of the stop

    Returns:
        LineStop object
    """
    return get_object_or_404(LineStop, line_id=line_id, stop_id=stop_id)


def get_lines_by_stop(stop_id):
    """
    Get lines that pass through a stop.

    Args:
        stop_id: ID of the stop

    Returns:
        Queryset of lines
    """
    line_ids = LineStop.objects.filter(stop_id=stop_id).values_list('line_id', flat=True)
    return Line.objects.filter(id__in=line_ids, is_active=True)


def get_active_lines():
    """
    Get all active lines.

    Returns:
        Queryset of active lines
    """
    return Line.objects.filter(is_active=True)


def get_active_stops():
    """
    Get all active stops.

    Returns:
        Queryset of active stops
    """
    return Stop.objects.filter(is_active=True)


def get_nearby_stops(latitude, longitude, radius_km=0.5):
    """
    Get stops near a location.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
        radius_km: Radius in kilometers

    Returns:
        Queryset of nearby stops
    """
    try:
        # This is a simplified approach without spatial database
        # In production, you would use PostGIS for better performance

        # Convert latitude/longitude to float
        lat = float(latitude)
        lon = float(longitude)

        # Get all active stops
        stops = Stop.objects.filter(is_active=True)

        # Filter stops by distance (naive approach)
        nearby_stops = []
        for stop in stops:
            distance = calculate_distance(
                lat, lon, float(stop.latitude), float(stop.longitude)
            )
            if distance is not None and distance <= radius_km:
                stop.distance = distance
                nearby_stops.append(stop)

        # Sort by distance
        nearby_stops.sort(key=lambda x: x.distance)

        return nearby_stops

    except Exception as e:
        logger.error(f"Error getting nearby stops: {e}")
        return []


def search_lines(query):
    """
    Search for lines by name or code.

    Args:
        query: Search query

    Returns:
        Queryset of matching lines
    """
    return Line.objects.filter(
        Q(name__icontains=query) |
        Q(code__icontains=query) |
        Q(description__icontains=query)
    ).filter(is_active=True)


def search_stops(query):
    """
    Search for stops by name or address.

    Args:
        query: Search query

    Returns:
        Queryset of matching stops
    """
    return Stop.objects.filter(
        Q(name__icontains=query) |
        Q(address__icontains=query)
    ).filter(is_active=True)


def get_line_schedule(line_id, day_of_week=None):
    """
    Get schedule for a line.

    Args:
        line_id: ID of the line
        day_of_week: Optional day of week (0-6, where 0 is Monday)

    Returns:
        Queryset of schedules
    """
    queryset = Schedule.objects.filter(line_id=line_id, is_active=True)

    if day_of_week is not None:
        queryset = queryset.filter(day_of_week=day_of_week)

    return queryset.order_by('day_of_week', 'start_time')


def get_next_stops(line_id, current_stop_id):
    """
    Get next stops in a line after a given stop.

    Args:
        line_id: ID of the line
        current_stop_id: ID of the current stop

    Returns:
        Queryset of next stops
    """
    try:
        # Get current stop order
        current_order = LineStop.objects.get(
            line_id=line_id,
            stop_id=current_stop_id
        ).order

        # Get next stops
        next_line_stops = LineStop.objects.filter(
            line_id=line_id,
            order__gt=current_order
        ).order_by('order')

        # Get stop IDs
        stop_ids = next_line_stops.values_list('stop_id', flat=True)

        return Stop.objects.filter(id__in=stop_ids)

    except Exception as e:
        logger.error(f"Error getting next stops: {e}")
        return Stop.objects.none()


def get_previous_stops(line_id, current_stop_id):
    """
    Get previous stops in a line before a given stop.

    Args:
        line_id: ID of the line
        current_stop_id: ID of the current stop

    Returns:
        Queryset of previous stops
    """
    try:
        # Get current stop order
        current_order = LineStop.objects.get(
            line_id=line_id,
            stop_id=current_stop_id
        ).order

        # Get previous stops
        prev_line_stops = LineStop.objects.filter(
            line_id=line_id,
            order__lt=current_order
        ).order_by('-order')

        # Get stop IDs
        stop_ids = prev_line_stops.values_list('stop_id', flat=True)

        return Stop.objects.filter(id__in=stop_ids)

    except Exception as e:
        logger.error(f"Error getting previous stops: {e}")
        return Stop.objects.none()


def get_busiest_stops(limit=10):
    """
    Get the busiest stops based on how many lines pass through them.

    Args:
        limit: Maximum number of stops to return

    Returns:
        Queryset of stops
    """
    stop_counts = LineStop.objects.values('stop_id').annotate(
        line_count=Count('line_id')
    ).order_by('-line_count')[:limit]

    stop_ids = [item['stop_id'] for item in stop_counts]
    stop_dict = {s.id: s for s in Stop.objects.filter(id__in=stop_ids)}

    # Maintain order from the count query
    result = []
    for item in stop_counts:
        stop = stop_dict.get(item['stop_id'])
        if stop:
            stop.line_count = item['line_count']
            result.append(stop)

    return result


def get_stop_distance(line_id, from_stop_id, to_stop_id):
    """
    Get the distance between two stops on a line.

    Args:
        line_id: ID of the line
        from_stop_id: ID of the starting stop
        to_stop_id: ID of the ending stop

    Returns:
        Distance in meters
    """
    try:
        # Get stop orders
        from_order = LineStop.objects.get(
            line_id=line_id,
            stop_id=from_stop_id
        ).order

        to_order = LineStop.objects.get(
            line_id=line_id,
            stop_id=to_stop_id
        ).order

        # Ensure from_order < to_order
        if from_order > to_order:
            from_order, to_order = to_order, from_order

        # Get line stops between from and to (inclusive)
        line_stops = LineStop.objects.filter(
            line_id=line_id,
            order__gte=from_order,
            order__lte=to_order
        ).order_by('order')

        # Calculate total distance
        total_distance = 0
        for i in range(1, len(line_stops)):
            distance = line_stops[i].distance_from_previous
            if distance:
                total_distance += distance

        return total_distance

    except Exception as e:
        logger.error(f"Error calculating stop distance: {e}")
        return None