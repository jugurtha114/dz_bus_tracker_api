from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Sum, Min, Max, F, ExpressionWrapper, fields

from apps.core.exceptions import ValidationError, ObjectNotFound
from .models import Passenger, SavedLocation, TripHistory, FeedbackRequest


def create_passenger(user):
    passenger = Passenger.objects.create(
        user=user
    )
    
    # Set user type to passenger if not already set
    if user.user_type != 'passenger':
        user.user_type = 'passenger'
        user.save(update_fields=['user_type'])
    
    return passenger


def update_passenger(passenger_id, data):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(passenger, field):
            setattr(passenger, field, value)
    
    passenger.save()
    
    return passenger


def update_notification_preferences(passenger_id, preferences):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    # Update notification preferences
    if not passenger.notification_preferences:
        passenger.notification_preferences = {}
    
    passenger.notification_preferences.update(preferences)
    passenger.save(update_fields=['notification_preferences'])
    
    return passenger


def add_saved_location(passenger_id, location_data):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    # Create saved location
    saved_location = SavedLocation.objects.create(
        passenger=passenger,
        name=location_data.get('name'),
        latitude=location_data.get('latitude'),
        longitude=location_data.get('longitude'),
        address=location_data.get('address', ''),
        is_favorite=location_data.get('is_favorite', False)
    )
    
    return saved_location


def update_saved_location(location_id, data):
    try:
        location = SavedLocation.objects.get(id=location_id)
    except SavedLocation.DoesNotExist:
        raise ObjectNotFound("Saved location not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(location, field):
            setattr(location, field, value)
    
    location.save()
    
    return location


def delete_saved_location(location_id):
    try:
        location = SavedLocation.objects.get(id=location_id)
    except SavedLocation.DoesNotExist:
        raise ObjectNotFound("Saved location not found")
    
    location.delete()
    
    return True


def start_trip(passenger_id, line_id, start_stop_id, end_stop_id=None):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    try:
        from apps.lines.models import Line, Stop
        line = Line.objects.get(id=line_id)
        start_stop = Stop.objects.get(id=start_stop_id)
        end_stop = Stop.objects.get(id=end_stop_id) if end_stop_id else None
    except (Line.DoesNotExist, Stop.DoesNotExist):
        raise ObjectNotFound("Line or stop not found")
    
    # Create trip history
    trip = TripHistory.objects.create(
        passenger=passenger,
        line=line,
        start_stop=start_stop,
        end_stop=end_stop or start_stop,  # Default to same stop if not provided
        start_time=timezone.now(),
        status='started'
    )
    
    # Update journey count
    passenger.journey_count += 1
    passenger.save(update_fields=['journey_count'])
    
    return trip


def complete_trip(trip_id, end_stop_id=None):
    try:
        trip = TripHistory.objects.get(id=trip_id)
    except TripHistory.DoesNotExist:
        raise ObjectNotFound("Trip not found")
    
    # If trip is already completed or cancelled, do nothing
    if trip.status != 'started':
        return trip
    
    # Update end stop if provided
    if end_stop_id:
        try:
            from apps.lines.models import Stop
            end_stop = Stop.objects.get(id=end_stop_id)
            trip.end_stop = end_stop
        except Stop.DoesNotExist:
            raise ObjectNotFound("Stop not found")
    
    # Complete trip
    trip.end_time = timezone.now()
    trip.status = 'completed'
    trip.save(update_fields=['end_stop', 'end_time', 'status'])
    
    # Create feedback request
    create_feedback_request(trip.passenger.id, trip.line.id, trip.id)
    
    return trip


def cancel_trip(trip_id):
    try:
        trip = TripHistory.objects.get(id=trip_id)
    except TripHistory.DoesNotExist:
        raise ObjectNotFound("Trip not found")
    
    # If trip is already completed or cancelled, do nothing
    if trip.status != 'started':
        return trip
    
    # Cancel trip
    trip.end_time = timezone.now()
    trip.status = 'cancelled'
    trip.save(update_fields=['end_time', 'status'])
    
    return trip


def create_feedback_request(passenger_id, line_id, trip_id=None):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    try:
        from apps.lines.models import Line
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    trip = None
    if trip_id:
        try:
            trip = TripHistory.objects.get(id=trip_id)
        except TripHistory.DoesNotExist:
            pass
    
    # Set expiration (24 hours from now)
    expires_at = timezone.now() + timedelta(hours=24)
    
    # Create feedback request
    feedback_request = FeedbackRequest.objects.create(
        passenger=passenger,
        trip=trip,
        line=line,
        expires_at=expires_at,
        is_completed=False
    )
    
    # Notify passenger
    notify_feedback_request(feedback_request)
    
    return feedback_request


def complete_feedback_request(request_id):
    try:
        feedback_request = FeedbackRequest.objects.get(id=request_id)
    except FeedbackRequest.DoesNotExist:
        raise ObjectNotFound("Feedback request not found")
    
    # Complete request
    feedback_request.is_completed = True
    feedback_request.save(update_fields=['is_completed'])
    
    return feedback_request


def notify_feedback_request(feedback_request):
    from apps.notifications.services import send_notification
    
    # Send notification
    send_notification(
        user=feedback_request.passenger.user,
        notification_type='system',
        title='Share Your Feedback',
        message=f'How was your trip on {feedback_request.line.name}? Share your feedback!',
        data={
            'feedback_request_id': str(feedback_request.id),
            'line_id': str(feedback_request.line.id),
            'expires_at': feedback_request.expires_at.isoformat()
        }
    )
    
    return True


def get_passenger_stats(passenger_id):
    try:
        passenger = Passenger.objects.get(id=passenger_id)
    except Passenger.DoesNotExist:
        raise ObjectNotFound("Passenger not found")
    
    # Get trips
    trips = TripHistory.objects.filter(passenger=passenger)
    
    # Count trips
    total_trips = trips.count()
    completed_trips = trips.filter(status='completed').count()
    cancelled_trips = trips.filter(status='cancelled').count()
    
    # Get most used lines
    most_used_lines = trips.values(
        'line_id', 'line__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Get most used stops
    most_used_stops = trips.values(
        'start_stop_id', 'start_stop__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Calculate distance traveled
    from apps.lines.models import LineStop
    from utils.geo import calculate_distance
    
    total_distance = 0
    for trip in trips.filter(status='completed'):
        try:
            # Get stops in order
            line_stops = LineStop.objects.filter(
                line=trip.line
            ).select_related('stop').order_by('order')
            
            # Find start and end indices
            start_idx = next(
                (i for i, ls in enumerate(line_stops) if ls.stop_id == trip.start_stop_id), 
                None
            )
            end_idx = next(
                (i for i, ls in enumerate(line_stops) if ls.stop_id == trip.end_stop_id), 
                None
            )
            
            # Calculate distance between stops
            if start_idx is not None and end_idx is not None:
                for i in range(min(start_idx, end_idx), max(start_idx, end_idx)):
                    stop1 = line_stops[i].stop
                    stop2 = line_stops[i + 1].stop
                    
                    dist = calculate_distance(
                        (float(stop1.latitude), float(stop1.longitude)),
                        (float(stop2.latitude), float(stop2.longitude))
                    )
                    
                    total_distance += dist
        except Exception:
            # Skip if there was an error calculating distance
            continue
    
    # Calculate time traveled
    time_traveled = 0
    for trip in trips.filter(status='completed'):
        if trip.end_time and trip.start_time:
            time_traveled += (trip.end_time - trip.start_time).total_seconds() / 60  # minutes
    
    # Get first and last trip dates
    first_trip = trips.aggregate(Min('start_time'))['start_time__min']
    last_trip = trips.aggregate(Max('start_time'))['start_time__max']
    
    return {
        'total_trips': total_trips,
        'completed_trips': completed_trips,
        'cancelled_trips': cancelled_trips,
        'most_used_lines': [
            {'id': str(line['line_id']), 'name': line['line__name'], 'count': line['count']}
            for line in most_used_lines
        ],
        'most_used_stops': [
            {'id': str(stop['start_stop_id']), 'name': stop['start_stop__name'], 'count': stop['count']}
            for stop in most_used_stops
        ],
        'total_distance_traveled': total_distance,
        'total_time_traveled': time_traveled,
        'first_trip_date': first_trip,
        'last_trip_date': last_trip
    }
