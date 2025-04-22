from django.db.models import Q
from django.utils import timezone
from utils.cache import cached_result

from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest


@cached_result('passenger', timeout=60)
def get_passenger_by_id(passenger_id):
    try:
        return Passenger.objects.select_related(
            'user'
        ).get(id=passenger_id)
    except Passenger.DoesNotExist:
        return None


def get_passenger_for_user(user):
    try:
        return Passenger.objects.get(user=user)
    except Passenger.DoesNotExist:
        return None


def get_active_passengers():
    return Passenger.objects.filter(
        is_active=True,
        user__is_active=True
    ).select_related('user')


def get_saved_locations(passenger_id, is_favorite=None):
    locations = SavedLocation.objects.filter(
        passenger_id=passenger_id,
        is_active=True
    )
    
    if is_favorite is not None:
        locations = locations.filter(is_favorite=is_favorite)
    
    return locations.order_by('-is_favorite', 'name')


def get_saved_location_by_id(location_id):
    try:
        return SavedLocation.objects.select_related(
            'passenger', 'passenger__user'
        ).get(id=location_id)
    except SavedLocation.DoesNotExist:
        return None


def get_nearest_saved_location(passenger_id, latitude, longitude, max_distance=1000):
    from utils.geo import calculate_distance
    
    locations = get_saved_locations(passenger_id)
    
    nearest_location = None
    min_distance = float('inf')
    
    for location in locations:
        distance = calculate_distance(
            (float(latitude), float(longitude)),
            (float(location.latitude), float(location.longitude))
        )
        
        if distance < min_distance and distance <= max_distance:
            min_distance = distance
            nearest_location = location
    
    return nearest_location, min_distance if nearest_location else None


def get_trip_history(passenger_id, status=None, limit=None):
    trips = TripHistory.objects.filter(
        passenger_id=passenger_id,
        is_active=True
    ).select_related(
        'line', 'start_stop', 'end_stop'
    )
    
    if status:
        trips = trips.filter(status=status)
    
    trips = trips.order_by('-start_time')
    
    if limit:
        trips = trips[:limit]
    
    return trips


def get_trip_by_id(trip_id):
    try:
        return TripHistory.objects.select_related(
            'passenger', 'passenger__user', 'line', 'start_stop', 'end_stop'
        ).get(id=trip_id)
    except TripHistory.DoesNotExist:
        return None


def get_active_trips(passenger_id):
    return TripHistory.objects.filter(
        passenger_id=passenger_id,
        status='started',
        is_active=True
    ).select_related(
        'line', 'start_stop', 'end_stop'
    )


def get_recent_trips(passenger_id, days=7, limit=5):
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    return TripHistory.objects.filter(
        passenger_id=passenger_id,
        start_time__gte=start_date,
        is_active=True
    ).select_related(
        'line', 'start_stop', 'end_stop'
    ).order_by('-start_time')[:limit]


def get_feedback_requests(passenger_id, is_completed=None, is_expired=None):
    requests = FeedbackRequest.objects.filter(
        passenger_id=passenger_id,
        is_active=True
    ).select_related(
        'line', 'trip'
    )
    
    if is_completed is not None:
        requests = requests.filter(is_completed=is_completed)
    
    if is_expired is not None:
        now = timezone.now()
        if is_expired:
            requests = requests.filter(expires_at__lt=now)
        else:
            requests = requests.filter(expires_at__gte=now)
    
    return requests.order_by('-sent_at')


def get_feedback_request_by_id(request_id):
    try:
        return FeedbackRequest.objects.select_related(
            'passenger', 'passenger__user', 'line', 'trip'
        ).get(id=request_id)
    except FeedbackRequest.DoesNotExist:
        return None


def get_pending_feedback_requests(passenger_id):
    now = timezone.now()
    
    return FeedbackRequest.objects.filter(
        passenger_id=passenger_id,
        is_completed=False,
        expires_at__gte=now,
        is_active=True
    ).select_related(
        'line', 'trip'
    ).order_by('-sent_at')


def search_passengers(query):
    return Passenger.objects.filter(
        Q(user__email__icontains=query) |
        Q(user__first_name__icontains=query) |
        Q(user__last_name__icontains=query) |
        Q(user__phone_number__icontains=query)
    ).select_related('user')


def get_passengers_with_recent_activity(days=7, limit=20):
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Get passengers with recent trips
    passenger_ids = TripHistory.objects.filter(
        start_time__gte=start_date
    ).values_list('passenger_id', flat=True).distinct()
    
    return Passenger.objects.filter(
        id__in=passenger_ids,
        is_active=True
    ).select_related('user')[:limit]


def get_passengers_by_journey_count(min_count=10, limit=20):
    return Passenger.objects.filter(
        journey_count__gte=min_count,
        is_active=True
    ).select_related('user').order_by('-journey_count')[:limit]


def get_passengers_by_notification_status(channel, enabled=True):
    """
    Get passengers based on their notification preferences for a specific channel.
    
    Args:
        channel: Notification channel ('push', 'email', 'sms')
        enabled: Whether the channel should be enabled or disabled
        
    Returns:
        Queryset of matching passengers
    """
    # Build the filter condition for JSON field
    json_key = f'notification_preferences__{channel}_enabled'
    filter_kwargs = {json_key: enabled}
    
    return Passenger.objects.filter(
        **filter_kwargs,
        is_active=True
    ).select_related('user')
