from datetime import datetime, timedelta, time
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from apps.core.exceptions import ValidationError, ObjectNotFound
from .models import Schedule, ScheduleException, ScheduledTrip, MaintenanceSchedule


def create_schedule(data):
    line = data.get('line')
    bus = data.get('bus')
    driver = data.get('driver')
    
    # Validate ownership
    if bus.driver.id != driver.id:
        raise ValidationError("Bus does not belong to the driver")
    
    # Check for conflicts
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    days_of_week = data.get('days_of_week')
    
    if check_schedule_conflict(bus, None, days_of_week, start_time, end_time):
        raise ValidationError("Schedule conflicts with an existing schedule for this bus")
    
    if check_schedule_conflict(driver, None, days_of_week, start_time, end_time):
        raise ValidationError("Schedule conflicts with an existing schedule for this driver")
    
    # Create schedule
    schedule = Schedule.objects.create(
        line=line,
        bus=bus,
        driver=driver,
        start_time=start_time,
        end_time=end_time,
        days_of_week=days_of_week,
        frequency=data.get('frequency', 0),
        is_peak_hour=data.get('is_peak_hour', False)
    )
    
    # Generate scheduled trips if needed
    if data.get('generate_trips', False):
        date_range = data.get('date_range', 7)  # Default to 7 days
        generate_trips_for_schedule(schedule.id, date_range=date_range)
    
    return schedule


def update_schedule(schedule_id, data):
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        raise ObjectNotFound("Schedule not found")
    
    # Check if bus or driver changed
    if 'bus' in data and data['bus'] != schedule.bus:
        # Validate ownership
        if 'driver' in data:
            driver = data['driver']
        else:
            driver = schedule.driver
        
        if data['bus'].driver.id != driver.id:
            raise ValidationError("Bus does not belong to the driver")
    
    # Check for conflicts if time or days changed
    if ('start_time' in data or 'end_time' in data or 'days_of_week' in data):
        start_time = data.get('start_time', schedule.start_time)
        end_time = data.get('end_time', schedule.end_time)
        days_of_week = data.get('days_of_week', schedule.days_of_week)
        
        bus = data.get('bus', schedule.bus)
        if check_schedule_conflict(bus, schedule, days_of_week, start_time, end_time):
            raise ValidationError("Schedule conflicts with an existing schedule for this bus")
        
        driver = data.get('driver', schedule.driver)
        if check_schedule_conflict(driver, schedule, days_of_week, start_time, end_time):
            raise ValidationError("Schedule conflicts with an existing schedule for this driver")
    
    # Update fields
    for field, value in data.items():
        if hasattr(schedule, field):
            setattr(schedule, field, value)
    
    schedule.save()
    
    # Update future scheduled trips if needed
    if data.get('update_trips', False):
        update_future_trips(schedule)
    
    return schedule


def check_schedule_conflict(entity, exclude_schedule, days_of_week, start_time, end_time):
    """
    Check for schedule conflicts for a bus or driver.
    
    Args:
        entity: Bus or Driver instance
        exclude_schedule: Schedule to exclude from conflict check (for updates)
        days_of_week: List of days of week
        start_time: Start time
        end_time: End time
        
    Returns:
        True if conflict exists, False otherwise
    """
    # Get field name based on entity type
    from apps.buses.models import Bus
    from apps.drivers.models import Driver
    
    if isinstance(entity, Bus):
        field_name = 'bus'
    elif isinstance(entity, Driver):
        field_name = 'driver'
    else:
        raise ValueError("Entity must be Bus or Driver")
    
    # Build query
    query = Q(**{field_name: entity}) & Q(is_active=True)
    query &= Q(days_of_week__overlap=days_of_week)
    
    # Time overlap condition
    time_overlap = (
        (Q(start_time__lt=end_time) & Q(end_time__gt=start_time))
    )
    query &= time_overlap
    
    # Exclude current schedule for updates
    if exclude_schedule:
        query &= ~Q(id=exclude_schedule.id)
    
    # Check for conflict
    return Schedule.objects.filter(query).exists()


def create_schedule_exception(data):
    schedule = data.get('schedule')
    date = data.get('date')
    
    # Check if date is in schedule's days
    date_weekday = date.weekday()
    if date_weekday not in schedule.days_of_week:
        raise ValidationError("The date is not in the schedule's days of week")
    
    # Create exception
    exception = ScheduleException.objects.create(
        schedule=schedule,
        date=date,
        is_cancelled=data.get('is_cancelled', True),
        reason=data.get('reason', '')
    )
    
    # Cancel any scheduled trips
    if exception.is_cancelled:
        ScheduledTrip.objects.filter(
            schedule=schedule,
            date=date,
            status='scheduled'
        ).update(status='cancelled')
    
    return exception


def generate_trips_for_schedule(schedule_id, start_date=None, date_range=7):
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        raise ObjectNotFound("Schedule not found")
    
    # Default start date to today
    if start_date is None:
        start_date = timezone.now().date()
    
    # Calculate end date
    end_date = start_date + timedelta(days=date_range)
    
    # Get existing exceptions
    exceptions = ScheduleException.objects.filter(
        schedule=schedule,
        date__range=[start_date, end_date]
    )
    exception_dates = {ex.date for ex in exceptions if ex.is_cancelled}
    
    # Generate trips
    generated_trips = []
    current_date = start_date
    
    while current_date <= end_date:
        # Check if this day is in the schedule
        if current_date.weekday() in schedule.days_of_week:
            # Check for exceptions
            if current_date not in exception_dates:
                # Create datetime objects for start and end times
                start_datetime = datetime.combine(
                    current_date, 
                    schedule.start_time,
                    tzinfo=timezone.get_current_timezone()
                )
                end_datetime = datetime.combine(
                    current_date,
                    schedule.end_time,
                    tzinfo=timezone.get_current_timezone()
                )
                
                # Handle overnight schedules
                if schedule.end_time < schedule.start_time:
                    end_datetime += timedelta(days=1)
                
                # Create scheduled trip
                trip = ScheduledTrip.objects.create(
                    schedule=schedule,
                    date=current_date,
                    start_time=start_datetime,
                    end_time=end_datetime,
                    status='scheduled'
                )
                
                generated_trips.append(trip)
                
                # If frequency is set, create additional trips
                if schedule.frequency > 0:
                    freq_minutes = schedule.frequency
                    start_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute
                    end_minutes = schedule.end_time.hour * 60 + schedule.end_time.minute
                    
                    # Adjust for overnight schedules
                    if end_minutes < start_minutes:
                        end_minutes += 24 * 60
                    
                    # Calculate number of additional trips
                    trip_count = (end_minutes - start_minutes) // freq_minutes
                    
                    for i in range(1, trip_count):
                        trip_start_time = start_datetime + timedelta(minutes=i * freq_minutes)
                        trip_end_time = trip_start_time + (end_datetime - start_datetime)
                        
                        freq_trip = ScheduledTrip.objects.create(
                            schedule=schedule,
                            date=current_date,
                            start_time=trip_start_time,
                            end_time=trip_end_time,
                            status='scheduled'
                        )
                        
                        generated_trips.append(freq_trip)
        
        current_date += timedelta(days=1)
    
    return generated_trips


def update_future_trips(schedule):
    # Get future scheduled trips
    now = timezone.now()
    future_trips = ScheduledTrip.objects.filter(
        schedule=schedule,
        start_time__gte=now,
        status='scheduled'
    )
    
    # Update each trip
    for trip in future_trips:
        # Update times while preserving date
        trip_date = trip.start_time.date()
        
        # Create new datetime objects
        start_datetime = datetime.combine(
            trip_date, 
            schedule.start_time,
            tzinfo=timezone.get_current_timezone()
        )
        end_datetime = datetime.combine(
            trip_date,
            schedule.end_time,
            tzinfo=timezone.get_current_timezone()
        )
        
        # Handle overnight schedules
        if schedule.end_time < schedule.start_time:
            end_datetime += timedelta(days=1)
        
        # Update trip
        trip.start_time = start_datetime
        trip.end_time = end_datetime
        trip.save()
    
    return future_trips


def start_scheduled_trip(trip_id):
    try:
        trip = ScheduledTrip.objects.get(id=trip_id)
    except ScheduledTrip.DoesNotExist:
        raise ObjectNotFound("Scheduled trip not found")
    
    # Check if trip is in scheduled status
    if trip.status != 'scheduled':
        raise ValidationError(f"Trip is already {trip.get_status_display()}")
    
    # Create tracking session
    from apps.tracking.services import start_tracking_session
    
    tracking_session = start_tracking_session(
        driver=trip.schedule.driver,
        bus=trip.schedule.bus,
        line=trip.schedule.line,
        schedule=trip.schedule
    )
    
    # Update trip
    trip.status = 'in_progress'
    trip.tracking_session = tracking_session
    trip.actual_start_time = timezone.now()
    
    # Calculate delay
    if trip.actual_start_time > trip.start_time:
        delay = (trip.actual_start_time - trip.start_time).total_seconds() / 60
        trip.delay_minutes = int(delay)
        
        # Update status to delayed if significant delay
        if trip.delay_minutes >= 15:
            trip.status = 'delayed'
    
    trip.save()
    
    return trip


def complete_scheduled_trip(trip_id):
    try:
        trip = ScheduledTrip.objects.get(id=trip_id)
    except ScheduledTrip.DoesNotExist:
        raise ObjectNotFound("Scheduled trip not found")
    
    # Check if trip is in progress or delayed
    if trip.status not in ['in_progress', 'delayed']:
        raise ValidationError(f"Trip is not in progress (status: {trip.get_status_display()})")
    
    # End tracking session if exists
    if trip.tracking_session:
        from apps.tracking.services import end_tracking_session
        tracking_session = end_tracking_session(trip.tracking_session.id)
    
    # Update trip
    trip.status = 'completed'
    trip.actual_end_time = timezone.now()
    trip.save()
    
    return trip


def cancel_scheduled_trip(trip_id, reason=''):
    try:
        trip = ScheduledTrip.objects.get(id=trip_id)
    except ScheduledTrip.DoesNotExist:
        raise ObjectNotFound("Scheduled trip not found")
    
    # Check if trip can be cancelled
    if trip.status not in ['scheduled', 'in_progress', 'delayed']:
        raise ValidationError(f"Trip cannot be cancelled (status: {trip.get_status_display()})")
    
    # End tracking session if exists and trip is in progress
    if trip.status in ['in_progress', 'delayed'] and trip.tracking_session:
        from apps.tracking.services import end_tracking_session
        tracking_session = end_tracking_session(trip.tracking_session.id)
    
    # Update trip
    trip.status = 'cancelled'
    trip.notes = reason
    trip.save()
    
    return trip


def create_maintenance_schedule(data):
    bus = data.get('bus')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    # Check for overlapping maintenance
    if MaintenanceSchedule.objects.filter(
        bus=bus,
        is_active=True,
        is_completed=False,
        start_date__lte=end_date,
        end_date__gte=start_date
    ).exists():
        raise ValidationError("Maintenance schedule overlaps with an existing one")
    
    # Create maintenance schedule
    maintenance = MaintenanceSchedule.objects.create(
        bus=bus,
        start_date=start_date,
        end_date=end_date,
        maintenance_type=data.get('maintenance_type'),
        description=data.get('description', ''),
        notes=data.get('notes', '')
    )
    
    # Cancel scheduled trips during maintenance
    cancel_trips_for_maintenance(maintenance)
    
    return maintenance


def update_maintenance_schedule(maintenance_id, data):
    try:
        maintenance = MaintenanceSchedule.objects.get(id=maintenance_id)
    except MaintenanceSchedule.DoesNotExist:
        raise ObjectNotFound("Maintenance schedule not found")
    
    # Check if dates changed
    date_changed = (
        ('start_date' in data and data['start_date'] != maintenance.start_date) or
        ('end_date' in data and data['end_date'] != maintenance.end_date)
    )
    
    if date_changed:
        start_date = data.get('start_date', maintenance.start_date)
        end_date = data.get('end_date', maintenance.end_date)
        
        # Check for overlapping maintenance
        if MaintenanceSchedule.objects.filter(
            bus=maintenance.bus,
            is_active=True,
            is_completed=False,
            start_date__lte=end_date,
            end_date__gte=start_date
        ).exclude(id=maintenance.id).exists():
            raise ValidationError("Maintenance schedule overlaps with an existing one")
    
    # Check if completed status changed
    was_completed = maintenance.is_completed
    will_be_completed = data.get('is_completed', was_completed)
    
    if not was_completed and will_be_completed:
        data['completed_at'] = data.get('completed_at', timezone.now())
    
    # Update fields
    for field, value in data.items():
        if hasattr(maintenance, field):
            setattr(maintenance, field, value)
    
    maintenance.save()
    
    # If dates changed, update affected trips
    if date_changed:
        cancel_trips_for_maintenance(maintenance)
    
    # Update bus's next_maintenance date if completed
    if will_be_completed and not was_completed:
        update_bus_maintenance_date(maintenance.bus)
    
    return maintenance


def complete_maintenance(maintenance_id):
    try:
        maintenance = MaintenanceSchedule.objects.get(id=maintenance_id)
    except MaintenanceSchedule.DoesNotExist:
        raise ObjectNotFound("Maintenance schedule not found")
    
    # Complete maintenance
    maintenance.is_completed = True
    maintenance.completed_at = timezone.now()
    maintenance.save()
    
    # Update bus's next_maintenance date
    update_bus_maintenance_date(maintenance.bus)
    
    return maintenance


def update_bus_maintenance_date(bus):
    from datetime import date
    from dateutil.relativedelta import relativedelta
    
    # Set next maintenance date based on bus type and last maintenance
    # This is a simplified example - actual logic may vary based on requirements
    today = date.today()
    
    # Default to 3 months from now
    next_maintenance = today + relativedelta(months=3)
    
    # Update bus
    bus.last_maintenance = today
    bus.next_maintenance = next_maintenance
    bus.save(update_fields=['last_maintenance', 'next_maintenance'])
    
    return bus


def cancel_trips_for_maintenance(maintenance):
    # Get all scheduled trips during maintenance period
    affected_trips = ScheduledTrip.objects.filter(
        schedule__bus=maintenance.bus,
        date__range=[maintenance.start_date, maintenance.end_date],
        status='scheduled'
    )
    
    # Cancel trips
    reason = f"Bus maintenance: {maintenance.get_maintenance_type_display()}"
    for trip in affected_trips:
        trip.status = 'cancelled'
        trip.notes = reason
        trip.save()
    
    return affected_trips


def get_calendar_data(start_date=None, end_date=None, bus_id=None, driver_id=None, line_id=None):
    """
    Get calendar data for the given date range and filters.
    
    Args:
        start_date: Start date (defaults to today)
        end_date: End date (defaults to 7 days from start)
        bus_id: Optional bus ID filter
        driver_id: Optional driver ID filter
        line_id: Optional line ID filter
        
    Returns:
        List of calendar day objects with trips, exceptions, and maintenance
    """
    from datetime import datetime, timedelta
    
    # Default dates
    if not start_date:
        start_date = timezone.now().date()
    
    if not end_date:
        end_date = start_date + timedelta(days=7)
    
    # Build query filters
    schedule_filter = Q(is_active=True)
    if bus_id:
        schedule_filter &= Q(bus_id=bus_id)
    if driver_id:
        schedule_filter &= Q(driver_id=driver_id)
    if line_id:
        schedule_filter &= Q(line_id=line_id)
    
    # Get schedules
    schedules = Schedule.objects.filter(schedule_filter)
    
    # Get scheduled trips
    trip_filter = Q(
        date__range=[start_date, end_date],
        schedule__in=schedules
    )
    trips = ScheduledTrip.objects.filter(trip_filter).select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver'
    )
    
    # Get schedule exceptions
    exception_filter = Q(
        date__range=[start_date, end_date],
        schedule__in=schedules
    )
    exceptions = ScheduleException.objects.filter(exception_filter).select_related(
        'schedule'
    )
    
    # Get maintenance schedules
    maintenance_filter = Q(
        start_date__lte=end_date,
        end_date__gte=start_date,
        is_active=True
    )
    if bus_id:
        maintenance_filter &= Q(bus_id=bus_id)
    
    maintenances = MaintenanceSchedule.objects.filter(maintenance_filter).select_related(
        'bus'
    )
    
    # Build calendar data
    calendar_data = []
    current_date = start_date
    
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    while current_date <= end_date:
        # Get day name
        day_name = days_of_week[current_date.weekday()]
        
        # Filter items for this day
        day_trips = [trip for trip in trips if trip.date == current_date]
        day_exceptions = [exc for exc in exceptions if exc.date == current_date]
        day_maintenances = [
            m for m in maintenances 
            if m.start_date <= current_date <= m.end_date
        ]
        
        # Add day to calendar
        calendar_data.append({
            'date': current_date,
            'day_name': day_name,
            'trips': day_trips,
            'exceptions': day_exceptions,
            'maintenance': day_maintenances
        })
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return calendar_data


def get_upcoming_trips(bus_id=None, driver_id=None, line_id=None, limit=10):
    """
    Get upcoming scheduled trips.
    
    Args:
        bus_id: Optional bus ID filter
        driver_id: Optional driver ID filter
        line_id: Optional line ID filter
        limit: Maximum number of trips to return
        
    Returns:
        Queryset of upcoming trips
    """
    now = timezone.now()
    
    # Build query filters
    trip_filter = Q(
        start_time__gte=now,
        status='scheduled',
        is_active=True
    )
    
    if bus_id:
        trip_filter &= Q(schedule__bus_id=bus_id)
    if driver_id:
        trip_filter &= Q(schedule__driver_id=driver_id)
    if line_id:
        trip_filter &= Q(schedule__line_id=line_id)
    
    # Get trips
    trips = ScheduledTrip.objects.filter(trip_filter).select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver'
    ).order_by('start_time')[:limit]
    
    return trips


def get_trip_conflicts(trip):
    """
    Get conflicts for a scheduled trip.
    
    Args:
        trip: ScheduledTrip instance
        
    Returns:
        List of conflicting trips and maintenance
    """
    conflicts = []
    
    # Check for other trips with the same bus or driver
    other_trips = ScheduledTrip.objects.filter(
        Q(schedule__bus=trip.schedule.bus) | Q(schedule__driver=trip.schedule.driver),
        date=trip.date,
        status__in=['scheduled', 'in_progress', 'delayed'],
        is_active=True
    ).exclude(id=trip.id)
    
    # Filter for time conflicts
    for other_trip in other_trips:
        # Check for time overlap
        if (
            other_trip.start_time < trip.end_time and
            other_trip.end_time > trip.start_time
        ):
            conflicts.append({
                'type': 'trip',
                'object': other_trip,
                'reason': (
                    f"Conflicts with trip on {other_trip.schedule.line.name}"
                    f" ({other_trip.start_time.time()} - {other_trip.end_time.time()})"
                )
            })
    
    # Check for maintenance conflicts
    maintenance_conflicts = MaintenanceSchedule.objects.filter(
        bus=trip.schedule.bus,
        start_date__lte=trip.date,
        end_date__gte=trip.date,
        is_completed=False,
        is_active=True
    )
    
    for maintenance in maintenance_conflicts:
        conflicts.append({
            'type': 'maintenance',
            'object': maintenance,
            'reason': (
                f"Bus scheduled for {maintenance.get_maintenance_type_display()} "
                f"maintenance ({maintenance.start_date} - {maintenance.end_date})"
            )
        })
    
    return conflicts