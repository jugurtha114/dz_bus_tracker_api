from django.db.models import Q, Count, Prefetch
from django.core.cache import cache

from apps.core.constants import CACHE_KEY_LINE_STOPS
from utils.cache import cached_result
from .models import Line, Stop, LineStop, LineBus, Favorite


@cached_result('line', timeout=60)
def get_line_by_id(line_id):
    try:
        return Line.objects.select_related(
            'start_location', 'end_location'
        ).prefetch_related(
            'line_stops', 'line_buses'
        ).get(id=line_id)
    except Line.DoesNotExist:
        return None


def get_line_by_name(name):
    try:
        return Line.objects.select_related(
            'start_location', 'end_location'
        ).get(name=name)
    except Line.DoesNotExist:
        return None


def get_active_lines():
    return Line.objects.filter(
        is_active=True
    ).select_related(
        'start_location', 'end_location'
    ).annotate(
        stops_count=Count('line_stops', distinct=True),
        active_buses_count=Count(
            'tracking_sessions',
            filter=Q(tracking_sessions__status='active', tracking_sessions__is_active=True),
            distinct=True
        )
    )


def get_lines_with_active_buses():
    from apps.tracking.models import TrackingSession
    
    # Get lines that have active tracking sessions
    active_sessions = TrackingSession.objects.filter(
        status='active',
        is_active=True
    ).values_list('line_id', flat=True)
    
    return Line.objects.filter(
        id__in=active_sessions,
        is_active=True
    ).select_related(
        'start_location', 'end_location'
    ).annotate(
        active_buses_count=Count(
            'tracking_sessions',
            filter=Q(tracking_sessions__status='active', tracking_sessions__is_active=True),
            distinct=True
        )
    )


@cached_result('line_stops', timeout=300)
def get_line_stops(line_id):
    return LineStop.objects.filter(
        line_id=line_id,
        is_active=True
    ).select_related(
        'stop'
    ).order_by('order')


def get_favorites_for_user(user):
    return Favorite.objects.filter(
        user=user,
        is_active=True
    ).select_related(
        'line', 'line__start_location', 'line__end_location'
    )


def is_line_favorited(user, line_id):
    return Favorite.objects.filter(
        user=user,
        line_id=line_id,
        is_active=True
    ).exists()


def get_stop_by_id(stop_id):
    try:
        return Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        return None


def get_stop_by_code(code):
    try:
        return Stop.objects.get(code=code)
    except Stop.DoesNotExist:
        return None


def get_nearest_stops(latitude, longitude, radius=1000, limit=5):
    from django.db.models.functions import ACos, Cos, Sin, Radians
    from django.db.models.expressions import F, Value
    
    # Convert latitude and longitude to radians
    lat_rad = float(latitude) * 3.14159 / 180
    lon_rad = float(longitude) * 3.14159 / 180
    
    # Calculate distance using Haversine formula
    stops = Stop.objects.annotate(
        distance=6371000 * ACos(
            Cos(Value(lat_rad)) * Cos(Radians(F('latitude'))) * Cos(Radians(F('longitude')) - Value(lon_rad)) +
            Sin(Value(lat_rad)) * Sin(Radians(F('latitude')))
        )
    ).filter(
        is_active=True,
        distance__lte=radius
    ).order_by('distance')[:limit]
    
    return stops


def get_lines_for_stop(stop_id):
    return Line.objects.filter(
        line_stops__stop_id=stop_id,
        is_active=True
    ).select_related(
        'start_location', 'end_location'
    ).annotate(
        stops_count=Count('line_stops', distinct=True),
        active_buses_count=Count(
            'tracking_sessions',
            filter=Q(tracking_sessions__status='active', tracking_sessions__is_active=True),
            distinct=True
        )
    )


def get_buses_for_line(line_id):
    return LineBus.objects.filter(
        line_id=line_id,
        is_active=True
    ).select_related('bus', 'bus__driver', 'bus__driver__user')


def search_lines(query):
    return Line.objects.filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(start_location__name__icontains=query) |
        Q(end_location__name__icontains=query)
    ).distinct().select_related(
        'start_location', 'end_location'
    ).annotate(
        stops_count=Count('line_stops', distinct=True),
        active_buses_count=Count(
            'tracking_sessions',
            filter=Q(tracking_sessions__status='active', tracking_sessions__is_active=True),
            distinct=True
        )
    )


def search_stops(query):
    return Stop.objects.filter(
        Q(name__icontains=query) |
        Q(code__icontains=query) |
        Q(address__icontains=query)
    ).distinct()


def get_connected_lines(start_stop_id, end_stop_id):
    """
    Find lines that connect two stops directly
    """
    # Find lines that contain both stops
    lines_with_start = set(LineStop.objects.filter(
        stop_id=start_stop_id
    ).values_list('line_id', flat=True))
    
    lines_with_end = set(LineStop.objects.filter(
        stop_id=end_stop_id
    ).values_list('line_id', flat=True))
    
    # Intersection gives lines that contain both stops
    connecting_line_ids = lines_with_start.intersection(lines_with_end)
    
    return Line.objects.filter(
        id__in=connecting_line_ids,
        is_active=True
    ).select_related(
        'start_location', 'end_location'
    )


def get_line_status(line_id):
    """
    Get the current status of a line, including active buses and next arrivals
    """
    from apps.tracking.selectors import get_latest_locations_for_line
    from apps.eta.selectors import get_next_arrivals_for_line
    
    try:
        line = Line.objects.get(id=line_id, is_active=True)
    except Line.DoesNotExist:
        return None
    
    # Get active buses
    active_buses = get_latest_locations_for_line(line_id)
    
    # Get next arrivals for stops
    next_arrivals = get_next_arrivals_for_line(line_id)
    
    return {
        'line_id': str(line.id),
        'name': line.name,
        'active_buses': len(active_buses),
        'buses': active_buses,
        'next_arrivals': next_arrivals
    }
