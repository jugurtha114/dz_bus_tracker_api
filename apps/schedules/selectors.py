from django.db.models import Q, Count, Prefetch
from django.utils import timezone

from utils.cache import cached_result
from .models import Schedule, ScheduleException, ScheduledTrip, MaintenanceSchedule


@cached_result('schedule', timeout=60)
def get_schedule_by_id(schedule_id):
    try:
        return Schedule.objects.select_related(
            'line', 'bus', 'driver'
        ).get(id=schedule_id)
    except Schedule.DoesNotExist:
        return None


def get_schedules_for_line(line_id):
    return Schedule.objects.filter(
        line_id=line_id,
        is_active=True
    ).select_related('bus', 'driver')


def get_schedules_for_bus(bus_id):
    return Schedule.objects.filter(
        bus_id=bus_id,
        is_active=True
    ).select_related('line', 'driver')


def get_schedules_for_driver(driver_id):
    return Schedule.objects.filter(
        driver_id=driver_id,
        is_active=True
    ).select_related('line', 'bus')


def get_peak_hour_schedules():
    return Schedule.objects.filter(
        is_peak_hour=True,
        is_active=True
    ).select_related('line', 'bus', 'driver')


def get_schedule_by_day(day_of_week):
    return Schedule.objects.filter(
        days_of_week__contains=[day_of_week],
        is_active=True
    ).select_related('line', 'bus', 'driver')


def get_schedule_exceptions(schedule_id=None, start_date=None, end_date=None):
    queryset = ScheduleException.objects.all()
    
    if schedule_id:
        queryset = queryset.filter(schedule_id=schedule_id)
    
    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    
    if end_date:
        queryset = queryset.filter(date__lte=end_date)
    
    return queryset.select_related('schedule').order_by('date')


@cached_result('scheduled_trip', timeout=60)
def get_scheduled_trip_by_id(trip_id):
    try:
        return ScheduledTrip.objects.select_related(
            'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver',
            'tracking_session'
        ).get(id=trip_id)
    except ScheduledTrip.DoesNotExist:
        return None


def get_scheduled_trips(
    schedule_id=None, bus_id=None, driver_id=None, line_id=None,
    start_date=None, end_date=None, status=None
):
    queryset = ScheduledTrip.objects.all()
    
    if schedule_id:
        queryset = queryset.filter(schedule_id=schedule_id)
    
    if bus_id:
        queryset = queryset.filter(schedule__bus_id=bus_id)
    
    if driver_id:
        queryset = queryset.filter(schedule__driver_id=driver_id)
    
    if line_id:
        queryset = queryset.filter(schedule__line_id=line_id)
    
    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    
    if end_date:
        queryset = queryset.filter(date__lte=end_date)
    
    if status:
        if isinstance(status, list):
            queryset = queryset.filter(status__in=status)
        else:
            queryset = queryset.filter(status=status)
    
    return queryset.select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver'
    ).order_by('date', 'start_time')


def get_active_trips():
    now = timezone.now()
    
    return ScheduledTrip.objects.filter(
        status__in=['in_progress', 'delayed'],
        start_time__lte=now,
        end_time__gte=now,
        is_active=True
    ).select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver',
        'tracking_session'
    )


def get_upcoming_trips(limit=10, hours_ahead=24):
    now = timezone.now()
    end_time = now + timezone.timedelta(hours=hours_ahead)
    
    return ScheduledTrip.objects.filter(
        status='scheduled',
        start_time__gte=now,
        start_time__lte=end_time,
        is_active=True
    ).select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver'
    ).order_by('start_time')[:limit]


def get_delayed_trips():
    return ScheduledTrip.objects.filter(
        status__in=['in_progress', 'delayed'],
        delay_minutes__gt=0,
        is_active=True
    ).select_related(
        'schedule', 'schedule__line', 'schedule__bus', 'schedule__driver'
    ).order_by('-delay_minutes')


@cached_result('maintenance_schedule', timeout=60)
def get_maintenance_by_id(maintenance_id):
    try:
        return MaintenanceSchedule.objects.select_related('bus').get(id=maintenance_id)
    except MaintenanceSchedule.DoesNotExist:
        return None


def get_maintenance_schedules(
    bus_id=None, start_date=None, end_date=None, maintenance_type=None,
    is_completed=None
):
    queryset = MaintenanceSchedule.objects.filter(is_active=True)
    
    if bus_id:
        queryset = queryset.filter(bus_id=bus_id)
    
    if start_date:
        queryset = queryset.filter(end_date__gte=start_date)
    
    if end_date:
        queryset = queryset.filter(start_date__lte=end_date)
    
    if maintenance_type:
        queryset = queryset.filter(maintenance_type=maintenance_type)
    
    if is_completed is not None:
        queryset = queryset.filter(is_completed=is_completed)
    
    return queryset.select_related('bus').order_by('start_date')


def get_current_maintenance_schedules():
    today = timezone.now().date()
    
    return MaintenanceSchedule.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        is_completed=False,
        is_active=True
    ).select_related('bus')


def get_overdue_maintenance_schedules():
    today = timezone.now().date()
    
    return MaintenanceSchedule.objects.filter(
        end_date__lt=today,
        is_completed=False,
        is_active=True
    ).select_related('bus')


def get_buses_due_for_maintenance(days_ahead=30):
    from datetime import date, timedelta
    
    from apps.buses.models import Bus
    
    # Calculate date threshold
    threshold_date = date.today() + timedelta(days=days_ahead)
    
    # Get buses with next_maintenance date within threshold
    return Bus.objects.filter(
        next_maintenance__lte=threshold_date,
        is_active=True,
        is_verified=True
    ).order_by('next_maintenance')


def get_schedule_conflicts(schedule, exclude_id=None):
    """
    Get conflicting schedules for the given schedule.
    
    Args:
        schedule: Schedule instance or dict with schedule attributes
        exclude_id: Optional schedule ID to exclude
        
    Returns:
        List of conflicting schedules
    """
    # Build filter for bus or driver conflicts
    if isinstance(schedule, Schedule):
        bus = schedule.bus
        driver = schedule.driver
        days_of_week = schedule.days_of_week
        start_time = schedule.start_time
        end_time = schedule.end_time
    else:
        bus = schedule.get('bus')
        driver = schedule.get('driver')
        days_of_week = schedule.get('days_of_week')
        start_time = schedule.get('start_time')
        end_time = schedule.get('end_time')
    
    # Bus conflicts
    bus_conflicts = Schedule.objects.filter(
        bus=bus,
        days_of_week__overlap=days_of_week,
        is_active=True
    )
    
    # Driver conflicts
    driver_conflicts = Schedule.objects.filter(
        driver=driver,
        days_of_week__overlap=days_of_week,
        is_active=True
    )
    
    # Combined conflicts
    conflicts = (bus_conflicts | driver_conflicts).distinct()
    
    # Exclude self if ID provided
    if exclude_id:
        conflicts = conflicts.exclude(id=exclude_id)
    
    # Filter for time conflicts
    time_conflicts = []
    for conflict in conflicts:
        # Check for time overlap
        if (
            conflict.start_time < end_time and
            conflict.end_time > start_time
        ):
            time_conflicts.append(conflict)
    
    return time_conflicts


def get_schedule_stats(schedule_id):
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return None
    
    # Get trips for this schedule
    trips = ScheduledTrip.objects.filter(schedule=schedule)
    
    # Count trips by status
    total_trips = trips.count()
    completed_trips = trips.filter(status='completed').count()
    cancelled_trips = trips.filter(status='cancelled').count()
    in_progress_trips = trips.filter(status__in=['in_progress', 'delayed']).count()
    
    # Calculate average delay
    avg_delay = trips.filter(
        status__in=['completed', 'in_progress', 'delayed']
    ).exclude(delay_minutes=0).aggregate(
        avg_delay=Avg('delay_minutes')
    )['avg_delay'] or 0
    
    return {
        'total_trips': total_trips,
        'completed_trips': completed_trips,
        'cancelled_trips': cancelled_trips,
        'in_progress_trips': in_progress_trips,
        'avg_delay_minutes': avg_delay,
        'schedule': schedule
    }
