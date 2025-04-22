import math
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from apps.core.exceptions import ValidationError, ObjectNotFound
from apps.core.constants import CACHE_KEY_ETA
from utils.geo import calculate_distance
from .models import ETA, ETANotification, StopArrival


def calculate_eta(tracking_session_id, stop_id):
    from apps.tracking.models import TrackingSession, LocationUpdate
    from apps.lines.models import LineStop, Stop
    
    try:
        tracking_session = TrackingSession.objects.select_related(
            'line', 'bus', 'driver'
        ).get(id=tracking_session_id, is_active=True)
    except TrackingSession.DoesNotExist:
        raise ObjectNotFound("Tracking session not found")
    
    try:
        stop = Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        raise ObjectNotFound("Stop not found")
    
    # Check if stop is in line
    try:
        line_stop = LineStop.objects.get(line=tracking_session.line, stop=stop)
    except LineStop.DoesNotExist:
        raise ValidationError("Stop is not in the line's route")
    
    # Get latest location update
    latest_location = LocationUpdate.objects.filter(
        session=tracking_session
    ).order_by('-timestamp').first()
    
    if not latest_location:
        raise ValidationError("No location updates available for this session")
    
    # Get line stops in order
    line_stops = LineStop.objects.filter(
        line=tracking_session.line
    ).select_related('stop').order_by('order')
    
    # Find the closest stop to the current location
    closest_stop = None
    min_distance = float('inf')
    
    for ls in line_stops:
        distance = calculate_distance(
            latest_location.coordinates,
            ls.stop.coordinates
        )
        
        if distance < min_distance:
            min_distance = distance
            closest_stop = ls
    
    # If target stop is before the closest stop, bus already passed it
    if line_stop.order <= closest_stop.order:
        # Bus already passed or is at the stop
        if line_stop.order < closest_stop.order:
            # Bus already passed the stop
            return None
        elif line_stop.order == closest_stop.order and min_distance < 50:
            # Bus is at the stop
            # Create or update ETA with actual arrival time
            eta, created = ETA.objects.update_or_create(
                tracking_session=tracking_session,
                line=tracking_session.line,
                bus=tracking_session.bus,
                stop=stop,
                defaults={
                    'estimated_arrival_time': timezone.now(),
                    'actual_arrival_time': timezone.now(),
                    'status': 'arrived',
                    'delay_minutes': 0,
                    'accuracy': 30,
                }
            )
            
            # Record stop arrival
            StopArrival.objects.create(
                tracking_session=tracking_session,
                line=tracking_session.line,
                stop=stop,
                bus=tracking_session.bus,
                arrival_time=timezone.now(),
                scheduled_arrival_time=None,
                delay_minutes=0
            )
            
            # Cache the ETA
            cache_key = CACHE_KEY_ETA.format(
                tracking_session.line.id,
                stop.id,
                tracking_session.bus.id
            )
            cache.set(cache_key, eta, timeout=3600)
            
            return eta
    
    # Calculate remaining distance
    remaining_distance = 0
    current_idx = None
    target_idx = None
    
    for idx, ls in enumerate(line_stops):
        if ls.id == closest_stop.id:
            current_idx = idx
        if ls.id == line_stop.id:
            target_idx = idx
    
    if current_idx is None or target_idx is None or current_idx >= target_idx:
        # Can't calculate - bus passed stop or indices invalid
        return None
    
    # Add distance from current location to closest stop
    remaining_distance += min_distance
    
    # Add distances between stops
    for idx in range(current_idx, target_idx):
        if idx + 1 < len(line_stops):
            stop1 = line_stops[idx].stop
            stop2 = line_stops[idx + 1].stop
            
            distance = calculate_distance(
                stop1.coordinates,
                stop2.coordinates
            )
            
            remaining_distance += distance
    
    # Calculate ETA based on average speed (historical or current)
    from apps.tracking.selectors import get_session_statistics
    
    stats = get_session_statistics(tracking_session.id)
    
    if stats and stats['average_speed'] > 0:
        # Use average speed from session statistics
        avg_speed = stats['average_speed']  # m/s
    else:
        # Default to 5 m/s (18 km/h)
        avg_speed = 5
    
    # Calculate time to arrival
    time_to_arrival_seconds = remaining_distance / avg_speed
    
    # Calculate estimated arrival time
    estimated_arrival_time = timezone.now() + timedelta(seconds=time_to_arrival_seconds)
    
    # Create or update ETA
    eta, created = ETA.objects.update_or_create(
        tracking_session=tracking_session,
        line=tracking_session.line,
        bus=tracking_session.bus,
        stop=stop,
        defaults={
            'estimated_arrival_time': estimated_arrival_time,
            'status': 'scheduled',
            'delay_minutes': 0,
            'accuracy': int(min(300, time_to_arrival_seconds * 0.1)),  # 10% of time to arrival, max 5 minutes
        }
    )
    
    # Cache the ETA
    cache_key = CACHE_KEY_ETA.format(
        tracking_session.line.id,
        stop.id,
        tracking_session.bus.id
    )
    cache.set(cache_key, eta, timeout=3600)
    
    return eta


def recalculate_etas_for_line(line_id):
    from apps.tracking.models import TrackingSession
    from apps.lines.models import Line, LineStop
    
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Get active tracking sessions for this line
    active_sessions = TrackingSession.objects.filter(
        line=line,
        status='active',
        is_active=True
    )
    
    # Get all stops for this line
    line_stops = LineStop.objects.filter(
        line=line
    ).select_related('stop').order_by('order')
    
    updated_etas = []
    
    for session in active_sessions:
        for line_stop in line_stops:
            try:
                eta = calculate_eta(session.id, line_stop.stop.id)
                if eta:
                    updated_etas.append(eta)
            except (ValidationError, ObjectNotFound):
                # Skip errors and continue with next stop
                continue
    
    return updated_etas


def should_recalculate_eta(line_id, location_update):
    # Get the timestamp of the last ETA calculation
    last_calculation_key = f'last_eta_calculation:{line_id}'
    last_calculation = cache.get(last_calculation_key)
    
    if not last_calculation:
        # No record of last calculation, so recalculate
        cache.set(last_calculation_key, timezone.now(), timeout=3600)
        return True
    
    # Calculate time since last calculation
    time_since_last = (timezone.now() - last_calculation).total_seconds()
    
    # Recalculate if it's been more than 60 seconds
    if time_since_last > 60:
        cache.set(last_calculation_key, timezone.now(), timeout=3600)
        return True
    
    # Check if speed or direction has changed significantly
    speed_change_key = f'last_speed:{location_update.session_id}'
    heading_change_key = f'last_heading:{location_update.session_id}'
    
    last_speed = cache.get(speed_change_key)
    last_heading = cache.get(heading_change_key)
    
    if last_speed is not None and last_heading is not None:
        # Check for significant changes
        speed_change = abs(location_update.speed - last_speed) if location_update.speed and last_speed else 0
        heading_change = abs(location_update.heading - last_heading) if location_update.heading and last_heading else 0
        
        if speed_change > 5 or heading_change > 30:  # 5 m/s or 30 degrees
            # Update cache and recalculate
            cache.set(speed_change_key, location_update.speed, timeout=3600)
            cache.set(heading_change_key, location_update.heading, timeout=3600)
            cache.set(last_calculation_key, timezone.now(), timeout=3600)
            return True
    
    # Update cache values
    cache.set(speed_change_key, location_update.speed, timeout=3600)
    cache.set(heading_change_key, location_update.heading, timeout=3600)
    
    return False


def record_stop_arrival(tracking_session_id, stop_id):
    from apps.tracking.models import TrackingSession
    from apps.lines.models import Stop
    
    try:
        tracking_session = TrackingSession.objects.select_related(
            'line', 'bus'
        ).get(id=tracking_session_id)
    except TrackingSession.DoesNotExist:
        raise ObjectNotFound("Tracking session not found")
    
    try:
        stop = Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        raise ObjectNotFound("Stop not found")
    
    # Get ETA for comparison
    eta = ETA.objects.filter(
        tracking_session=tracking_session,
        line=tracking_session.line,
        bus=tracking_session.bus,
        stop=stop,
        actual_arrival_time__isnull=True
    ).order_by('-created_at').first()
    
    now = timezone.now()
    scheduled_time = None
    delay_minutes = 0
    
    if eta:
        scheduled_time = eta.estimated_arrival_time
        if scheduled_time:
            # Calculate delay
            delay = (now - scheduled_time).total_seconds()
            delay_minutes = max(0, int(delay / 60))
            
            # Update ETA
            eta.actual_arrival_time = now
            eta.status = 'arrived'
            eta.delay_minutes = delay_minutes
            eta.save()
    
    # Create stop arrival record
    arrival = StopArrival.objects.create(
        tracking_session=tracking_session,
        line=tracking_session.line,
        stop=stop,
        bus=tracking_session.bus,
        arrival_time=now,
        scheduled_arrival_time=scheduled_time,
        delay_minutes=delay_minutes
    )
    
    return arrival


def update_stop_departure(arrival_id):
    try:
        arrival = StopArrival.objects.get(id=arrival_id)
    except StopArrival.DoesNotExist:
        raise ObjectNotFound("Stop arrival not found")
    
    # Record departure time
    arrival.departure_time = timezone.now()
    arrival.save()
    
    return arrival


def create_eta_notification(eta_id, user_id, threshold=5, notification_type='push'):
    from apps.authentication.models import User
    
    try:
        eta = ETA.objects.get(id=eta_id)
    except ETA.DoesNotExist:
        raise ObjectNotFound("ETA not found")
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise ObjectNotFound("User not found")
    
    # Create notification
    notification, created = ETANotification.objects.get_or_create(
        eta=eta,
        user=user,
        notification_type=notification_type,
        defaults={
            'notification_threshold': threshold,
            'is_sent': False
        }
    )
    
    if not created:
        # Update existing notification
        notification.notification_threshold = threshold
        notification.is_sent = False
        notification.sent_at = None
        notification.save()
    
    return notification


def send_eta_notifications():
    from apps.notifications.services import send_push_notification, send_sms_notification, send_email_notification
    
    # Get pending notifications
    now = timezone.now()
    pending_notifications = ETANotification.objects.filter(
        is_sent=False,
        is_active=True,
        eta__is_active=True,
        eta__status__in=['scheduled', 'approaching'],
        eta__estimated_arrival_time__gt=now
    ).select_related('eta', 'user', 'eta__stop', 'eta__line', 'eta__bus')
    
    sent_count = 0
    
    for notification in pending_notifications:
        # Calculate minutes remaining
        time_remaining = (notification.eta.estimated_arrival_time - now).total_seconds() / 60
        
        # Check if it's time to send the notification
        if time_remaining <= notification.notification_threshold:
            success = False
            
            # Format message
            message = f"Bus {notification.eta.bus.matricule} on line {notification.eta.line.name} will arrive at {notification.eta.stop.name} in {int(time_remaining)} minutes."
            
            # Send notification based on type
            if notification.notification_type == 'push':
                notification_id = send_push_notification(
                    user=notification.user,
                    title="Bus Arriving Soon",
                    message=message,
                    data={
                        'eta_id': str(notification.eta.id),
                        'line_id': str(notification.eta.line.id),
                        'stop_id': str(notification.eta.stop.id),
                        'bus_id': str(notification.eta.bus.id),
                        'minutes_remaining': int(time_remaining)
                    }
                )
                success = notification_id is not None
                notification.notification_id = notification_id or ''
            
            elif notification.notification_type == 'sms':
                success = send_sms_notification(
                    phone_number=notification.user.phone_number,
                    message=message
                )
            
            elif notification.notification_type == 'email':
                success = send_email_notification(
                    to_email=notification.user.email,
                    subject="Bus Arriving Soon",
                    message=message
                )
            
            # Mark as sent
            if success:
                notification.is_sent = True
                notification.sent_at = now
                notification.save()
                sent_count += 1
    
    return sent_count


def get_next_arrivals(stop_id, limit=5):
    from apps.lines.models import Stop
    from apps.tracking.selectors import get_current_location
    
    try:
        stop = Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        raise ObjectNotFound("Stop not found")
    
    # Get ETAs for this stop
    now = timezone.now()
    etas = ETA.objects.filter(
        stop=stop,
        estimated_arrival_time__gt=now,
        status__in=['scheduled', 'approaching'],
        is_active=True
    ).select_related(
        'line', 'bus', 'tracking_session'
    ).order_by('estimated_arrival_time')[:limit]
    
    arrivals = []
    
    for eta in etas:
        # Calculate minutes remaining
        minutes_remaining = math.ceil((eta.estimated_arrival_time - now).total_seconds() / 60)
        
        # Get current location
        location = get_current_location(eta.tracking_session.id)
        
        latitude = None
        longitude = None
        last_update = None
        
        if location:
            latitude = location.get('latitude')
            longitude = location.get('longitude')
            last_update = location.get('timestamp')
        
        # Build arrival data
        arrival = {
            'eta_id': eta.id,
            'line_id': eta.line.id,
            'line_name': eta.line.name,
            'bus_id': eta.bus.id,
            'bus_matricule': eta.bus.matricule,
            'stop_id': stop.id,
            'stop_name': stop.name,
            'estimated_arrival_time': eta.estimated_arrival_time,
            'minutes_remaining': minutes_remaining,
            'status': eta.status,
            'delay_minutes': eta.delay_minutes,
            'tracking_session_id': eta.tracking_session.id,
            'latitude': latitude,
            'longitude': longitude,
            'last_update': last_update
        }
        
        arrivals.append(arrival)
    
    return arrivals


def get_next_arrivals_for_line(line_id, limit=10):
    from apps.lines.models import Line, LineStop
    
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Get stops for this line
    line_stops = LineStop.objects.filter(
        line=line
    ).select_related('stop').order_by('order')
    
    all_arrivals = []
    
    for line_stop in line_stops:
        arrivals = get_next_arrivals(line_stop.stop.id, limit=2)
        all_arrivals.extend(arrivals)
    
    # Sort by arrival time and limit
    all_arrivals.sort(key=lambda x: x['estimated_arrival_time'])
    
    return all_arrivals[:limit]