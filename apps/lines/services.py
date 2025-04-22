from django.db import transaction
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import ValidationError, ObjectNotFound
from apps.core.constants import CACHE_KEY_LINE_STOPS
from utils.geo import calculate_distance
from .models import Line, Stop, LineStop, LineBus, Favorite


def create_line(data, stops_data=None):
    with transaction.atomic():
        # Create the line
        line = Line.objects.create(
            name=data.get('name'),
            description=data.get('description', ''),
            color=data.get('color', '#3498db'),
            start_location=data.get('start_location'),
            end_location=data.get('end_location'),
            path=data.get('path', {}),
            estimated_duration=data.get('estimated_duration', 0),
            distance=data.get('distance', 0),
            metadata=data.get('metadata', {}),
        )
        
        # Create line stops
        if stops_data:
            for i, stop_data in enumerate(stops_data):
                stop_id = stop_data.get('id')
                if not stop_id:
                    continue
                
                try:
                    stop = Stop.objects.get(id=stop_id)
                except Stop.DoesNotExist:
                    continue
                
                LineStop.objects.create(
                    line=line,
                    stop=stop,
                    order=i,
                    distance_from_start=stop_data.get('distance_from_start', 0),
                    estimated_time_from_start=stop_data.get('estimated_time_from_start', 0)
                )
        
        # Always add start and end locations as stops if not already added
        if not LineStop.objects.filter(line=line, stop=line.start_location).exists():
            LineStop.objects.create(
                line=line,
                stop=line.start_location,
                order=0,
                distance_from_start=0,
                estimated_time_from_start=0
            )
        
        if not LineStop.objects.filter(line=line, stop=line.end_location).exists():
            last_order = LineStop.objects.filter(line=line).order_by('-order').first()
            last_order = last_order.order + 1 if last_order else 1
            
            LineStop.objects.create(
                line=line,
                stop=line.end_location,
                order=last_order,
                distance_from_start=line.distance,
                estimated_time_from_start=line.estimated_duration * 60  # Convert to seconds
            )
        
        # Invalidate cache
        cache_key = CACHE_KEY_LINE_STOPS.format(line.id)
        cache.delete(cache_key)
        
        return line


def update_line(line_id, data):
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(line, field):
            setattr(line, field, value)
    
    line.save()
    
    # Invalidate cache
    cache_key = CACHE_KEY_LINE_STOPS.format(line.id)
    cache.delete(cache_key)
    
    return line


def add_stop_to_line(line_id, stop_id, order=None, distance_from_start=0, estimated_time_from_start=0):
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    try:
        stop = Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        raise ObjectNotFound("Stop not found")
    
    # Check if stop is already in line
    if LineStop.objects.filter(line=line, stop=stop).exists():
        raise ValidationError("Stop is already in this line")
    
    # If order not provided, add at end
    if order is None:
        last_stop = LineStop.objects.filter(line=line).order_by('-order').first()
        order = last_stop.order + 1 if last_stop else 0
    else:
        # If order provided, shift other stops
        LineStop.objects.filter(line=line, order__gte=order).update(
            order=models.F('order') + 1
        )
    
    # Create line stop
    line_stop = LineStop.objects.create(
        line=line,
        stop=stop,
        order=order,
        distance_from_start=distance_from_start,
        estimated_time_from_start=estimated_time_from_start
    )
    
    # Invalidate cache
    cache_key = CACHE_KEY_LINE_STOPS.format(line.id)
    cache.delete(cache_key)
    
    return line_stop


def remove_stop_from_line(line_id, stop_id):
    try:
        line_stop = LineStop.objects.get(line_id=line_id, stop_id=stop_id)
    except LineStop.DoesNotExist:
        raise ObjectNotFound("Stop not found in this line")
    
    # Cannot remove start or end location
    if line_stop.stop_id == line_stop.line.start_location_id or line_stop.stop_id == line_stop.line.end_location_id:
        raise ValidationError("Cannot remove start or end location from line")
    
    # Get the order for shifting
    order = line_stop.order
    
    # Delete the line stop
    line_stop.delete()
    
    # Shift other stops
    LineStop.objects.filter(line_id=line_id, order__gt=order).update(
        order=models.F('order') - 1
    )
    
    # Invalidate cache
    cache_key = CACHE_KEY_LINE_STOPS.format(line_id)
    cache.delete(cache_key)
    
    return True


def reorder_line_stops(line_id, stop_orders):
    """
    Reorder stops in a line
    
    Args:
        line_id: ID of the line
        stop_orders: Dictionary mapping stop IDs to new orders
    """
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Validate that all stops exist
    for stop_id in stop_orders.keys():
        if not LineStop.objects.filter(line=line, stop_id=stop_id).exists():
            raise ObjectNotFound(f"Stop with ID {stop_id} not found in this line")
    
    # Start and end locations must be first and last
    start_location_id = str(line.start_location_id)
    end_location_id = str(line.end_location_id)
    
    if start_location_id in stop_orders and stop_orders[start_location_id] != 0:
        raise ValidationError("Start location must be the first stop")
    
    # Find the highest order
    max_order = max(stop_orders.values())
    
    if end_location_id in stop_orders and stop_orders[end_location_id] != max_order:
        raise ValidationError("End location must be the last stop")
    
    # Update orders
    with transaction.atomic():
        for stop_id, order in stop_orders.items():
            LineStop.objects.filter(line=line, stop_id=stop_id).update(order=order)
    
    # Invalidate cache
    cache_key = CACHE_KEY_LINE_STOPS.format(line_id)
    cache.delete(cache_key)
    
    return True


def create_stop(data):
    # Create stop
    stop = Stop.objects.create(
        name=data.get('name'),
        code=data.get('code', ''),
        address=data.get('address', ''),
        image=data.get('image'),
        description=data.get('description', ''),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        accuracy=data.get('accuracy'),
        metadata=data.get('metadata', {}),
    )
    
    return stop


def update_stop(stop_id, data):
    try:
        stop = Stop.objects.get(id=stop_id)
    except Stop.DoesNotExist:
        raise ObjectNotFound("Stop not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(stop, field):
            setattr(stop, field, value)
    
    stop.save()
    
    # Invalidate caches for lines containing this stop
    for line_stop in stop.line_stops.all():
        cache_key = CACHE_KEY_LINE_STOPS.format(line_stop.line_id)
        cache.delete(cache_key)
    
    return stop


def add_bus_to_line(line_id, bus_id, is_primary=False):
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Check if bus is already in line
    if LineBus.objects.filter(line=line, bus=bus).exists():
        raise ValidationError("Bus is already in this line")
    
    # If setting as primary, unset any other primary buses on this line
    if is_primary:
        LineBus.objects.filter(line=line, is_primary=True).update(is_primary=False)
    
    # Create line bus
    line_bus = LineBus.objects.create(
        line=line,
        bus=bus,
        is_primary=is_primary
    )
    
    return line_bus


def remove_bus_from_line(line_id, bus_id):
    try:
        line_bus = LineBus.objects.get(line_id=line_id, bus_id=bus_id)
    except LineBus.DoesNotExist:
        raise ObjectNotFound("Bus not found in this line")
    
    # Delete the line bus
    line_bus.delete()
    
    return True


def add_favorite(user, line_id, notification_threshold=5):
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Check if already favorited
    if Favorite.objects.filter(user=user, line=line).exists():
        raise ValidationError("Line is already in favorites")
    
    # Create favorite
    favorite = Favorite.objects.create(
        user=user,
        line=line,
        notification_threshold=notification_threshold
    )
    
    return favorite


def remove_favorite(user, line_id):
    try:
        favorite = Favorite.objects.get(user=user, line_id=line_id)
    except Favorite.DoesNotExist:
        raise ObjectNotFound("Line not found in favorites")
    
    # Delete the favorite
    favorite.delete()
    
    return True


def update_favorite_threshold(user, line_id, notification_threshold):
    try:
        favorite = Favorite.objects.get(user=user, line_id=line_id)
    except Favorite.DoesNotExist:
        raise ObjectNotFound("Line not found in favorites")
    
    # Update threshold
    favorite.notification_threshold = notification_threshold
    favorite.save()
    
    return favorite


def calculate_line_path(line_id):
    """
    Calculate a GeoJSON path for a line based on its stops
    """
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Get stops in order
    stops = line.get_ordered_stops()
    
    if len(stops) < 2:
        raise ValidationError("Line must have at least two stops")
    
    # Create path
    coordinates = [(float(stop.longitude), float(stop.latitude)) for stop in stops]
    
    path = {
        "type": "LineString",
        "coordinates": coordinates
    }
    
    # Update line
    line.path = path
    line.save()
    
    return path


def calculate_line_distances(line_id):
    """
    Calculate distances and times between stops on a line
    """
    try:
        line = Line.objects.get(id=line_id)
    except Line.DoesNotExist:
        raise ObjectNotFound("Line not found")
    
    # Get stops in order
    line_stops = line.line_stops.all().order_by('order')
    
    if line_stops.count() < 2:
        raise ValidationError("Line must have at least two stops")
    
    # Calculate distances
    total_distance = 0
    prev_stop = None
    
    for line_stop in line_stops:
        if prev_stop:
            distance = calculate_distance(
                prev_stop.stop.coordinates,
                line_stop.stop.coordinates
            )
            total_distance += distance
            
            # Update distance from start
            line_stop.distance_from_start = total_distance
            line_stop.save()
        
        prev_stop = line_stop
    
    # Update line distance
    line.distance = total_distance
    
    # Estimate duration (assuming average speed of 20 km/h)
    avg_speed = 20  # km/h
    duration_minutes = (total_distance / 1000) / avg_speed * 60
    line.estimated_duration = int(duration_minutes)
    
    line.save()
    
    # Calculate estimated times
    for line_stop in line_stops:
        # Calculate time in seconds
        time_seconds = (line_stop.distance_from_start / total_distance) * line.estimated_duration * 60
        line_stop.estimated_time_from_start = int(time_seconds)
        line_stop.save()
    
    return line
