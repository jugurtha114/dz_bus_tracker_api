from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q

from apps.core.constants import CACHE_KEY_ETA
from utils.cache import cached_result
from .models import ETA, ETANotification, StopArrival


@cached_result('eta', timeout=30)
def get_eta_by_id(eta_id):
    try:
        return ETA.objects.select_related(
            'line', 'bus', 'stop', 'tracking_session'
        ).get(id=eta_id)
    except ETA.DoesNotExist:
        return None


def get_eta_for_bus_stop(bus_id, stop_id):
    now = timezone.now()
    
    try:
        eta = ETA.objects.filter(
            bus_id=bus_id,
            stop_id=stop_id,
            estimated_arrival_time__gt=now,
            is_active=True
        ).order_by('estimated_arrival_time').first()
        
        return eta
    except ETA.DoesNotExist:
        return None


def get_eta_from_cache(line_id, stop_id, bus_id):
    cache_key = CACHE_KEY_ETA.format(line_id, stop_id, bus_id)
    return cache.get(cache_key)


def get_etas_for_stop(stop_id, limit=10):
    now = timezone.now()
    
    return ETA.objects.filter(
        stop_id=stop_id,
        estimated_arrival_time__gt=now,
        status__in=['scheduled', 'approaching'],
        is_active=True
    ).select_related(
        'line', 'bus', 'tracking_session'
    ).order_by('estimated_arrival_time')[:limit]


def get_etas_for_line(line_id, limit=20):
    now = timezone.now()
    
    return ETA.objects.filter(
        line_id=line_id,
        estimated_arrival_time__gt=now,
        status__in=['scheduled', 'approaching'],
        is_active=True
    ).select_related(
        'stop', 'bus', 'tracking_session'
    ).order_by('estimated_arrival_time')[:limit]


def get_etas_for_bus(bus_id, limit=20):
    now = timezone.now()
    
    return ETA.objects.filter(
        bus_id=bus_id,
        estimated_arrival_time__gt=now,
        status__in=['scheduled', 'approaching'],
        is_active=True
    ).select_related(
        'line', 'stop', 'tracking_session'
    ).order_by('estimated_arrival_time')[:limit]


def get_etas_for_session(tracking_session_id):
    now = timezone.now()
    
    return ETA.objects.filter(
        tracking_session_id=tracking_session_id,
        estimated_arrival_time__gt=now,
        is_active=True
    ).select_related(
        'line', 'bus', 'stop'
    ).order_by('estimated_arrival_time')


def get_eta_notifications_for_user(user_id, sent=None, limit=20):
    queryset = ETANotification.objects.filter(
        user_id=user_id,
        is_active=True
    ).select_related(
        'eta', 'eta__line', 'eta__bus', 'eta__stop'
    )
    
    if sent is not None:
        queryset = queryset.filter(is_sent=sent)
    
    return queryset.order_by('-created_at')[:limit]


def get_arrivals_for_stop(stop_id, start_time=None, end_time=None, limit=20):
    queryset = StopArrival.objects.filter(
        stop_id=stop_id,
        is_active=True
    ).select_related(
        'tracking_session', 'line', 'bus'
    )
    
    if start_time:
        queryset = queryset.filter(arrival_time__gte=start_time)
    
    if end_time:
        queryset = queryset.filter(arrival_time__lte=end_time)
    
    return queryset.order_by('-arrival_time')[:limit]


def get_arrivals_for_bus(bus_id, start_time=None, end_time=None, limit=20):
    queryset = StopArrival.objects.filter(
        bus_id=bus_id,
        is_active=True
    ).select_related(
        'tracking_session', 'line', 'stop'
    )
    
    if start_time:
        queryset = queryset.filter(arrival_time__gte=start_time)
    
    if end_time:
        queryset = queryset.filter(arrival_time__lte=end_time)
    
    return queryset.order_by('-arrival_time')[:limit]


def get_arrivals_for_line(line_id, start_time=None, end_time=None, limit=20):
    queryset = StopArrival.objects.filter(
        line_id=line_id,
        is_active=True
    ).select_related(
        'tracking_session', 'bus', 'stop'
    )
    
    if start_time:
        queryset = queryset.filter(arrival_time__gte=start_time)
    
    if end_time:
        queryset = queryset.filter(arrival_time__lte=end_time)
    
    return queryset.order_by('-arrival_time')[:limit]


def get_arrivals_for_session(tracking_session_id):
    return StopArrival.objects.filter(
        tracking_session_id=tracking_session_id,
        is_active=True
    ).select_related(
        'line', 'bus', 'stop'
    ).order_by('arrival_time')


def get_delayed_etas(delay_threshold=5, limit=20):
    now = timezone.now()
    
    return ETA.objects.filter(
        estimated_arrival_time__gt=now,
        delay_minutes__gte=delay_threshold,
        status__in=['scheduled', 'approaching', 'delayed'],
        is_active=True
    ).select_related(
        'line', 'bus', 'stop', 'tracking_session'
    ).order_by('-delay_minutes')[:limit]


def get_pending_eta_notifications(limit=100):
    now = timezone.now()
    
    return ETANotification.objects.filter(
        is_sent=False,
        is_active=True,
        eta__is_active=True,
        eta__status__in=['scheduled', 'approaching'],
        eta__estimated_arrival_time__gt=now
    ).select_related(
        'eta', 'user', 'eta__stop', 'eta__line', 'eta__bus'
    ).order_by('eta__estimated_arrival_time')[:limit]


def get_next_arrivals_for_line(line_id, limit=10):
    from apps.eta.services import get_next_arrivals_for_line as service_get_next_arrivals_for_line
    
    try:
        return service_get_next_arrivals_for_line(line_id, limit)
    except Exception:
        # Return empty list on error
        return []
