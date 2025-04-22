from django.db.models import Q, Count, Prefetch
from django.core.cache import cache

from utils.cache import cached_result
from .models import Bus, BusPhoto, BusVerification, BusMaintenance


@cached_result('bus', timeout=60)
def get_bus_by_id(bus_id):
    try:
        return Bus.objects.select_related(
            'driver', 'driver__user'
        ).prefetch_related(
            'photos', 'verifications'
        ).get(id=bus_id)
    except Bus.DoesNotExist:
        return None


def get_bus_by_matricule(matricule):
    try:
        return Bus.objects.select_related(
            'driver', 'driver__user'
        ).get(matricule=matricule)
    except Bus.DoesNotExist:
        return None


def get_buses_for_driver(driver_id):
    return Bus.objects.filter(
        driver_id=driver_id
    ).select_related(
        'driver', 'driver__user'
    ).prefetch_related('photos')


def get_active_buses():
    return Bus.objects.filter(
        is_active=True, 
        is_verified=True
    ).select_related(
        'driver', 'driver__user'
    )


def get_buses_by_verification_status(status):
    # Get the latest verification record for each bus
    latest_verifications = BusVerification.objects.filter(
        status=status
    ).values('bus').annotate(
        latest_id=Count('id')
    ).values('bus')
    
    # Get buses with latest verification having the specified status
    return Bus.objects.filter(
        id__in=latest_verifications
    ).select_related(
        'driver', 'driver__user'
    ).prefetch_related(
        Prefetch(
            'verifications',
            queryset=BusVerification.objects.filter(status=status).order_by('-created_at'),
            to_attr='latest_verifications'
        )
    )


def get_buses_requiring_maintenance():
    from django.utils import timezone
    
    # Get buses with next maintenance date in the past or today
    return Bus.objects.filter(
        is_active=True,
        next_maintenance__lte=timezone.now().date()
    ).select_related(
        'driver', 'driver__user'
    )


def get_active_tracking_buses():
    from apps.tracking.models import TrackingSession
    
    # Get buses that are currently being tracked
    active_sessions = TrackingSession.objects.filter(
        status='active',
        is_active=True
    ).values_list('bus_id', flat=True)
    
    return Bus.objects.filter(
        id__in=active_sessions,
        is_active=True
    ).select_related(
        'driver', 'driver__user'
    )


def get_bus_photos(bus_id, photo_type=None):
    queryset = BusPhoto.objects.filter(bus_id=bus_id)
    
    if photo_type:
        queryset = queryset.filter(photo_type=photo_type)
    
    return queryset


def get_bus_maintenance_records(bus_id, start_date=None, end_date=None):
    queryset = BusMaintenance.objects.filter(bus_id=bus_id)
    
    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    
    if end_date:
        queryset = queryset.filter(date__lte=end_date)
    
    return queryset.order_by('-date')


def filter_buses(query=None, driver_id=None, brand=None, model=None, is_verified=None, is_active=None):
    queryset = Bus.objects.all()
    
    if query:
        queryset = queryset.filter(
            Q(matricule__icontains=query) | 
            Q(brand__icontains=query) | 
            Q(model__icontains=query)
        )
    
    if driver_id:
        queryset = queryset.filter(driver_id=driver_id)
    
    if brand:
        queryset = queryset.filter(brand__icontains=brand)
    
    if model:
        queryset = queryset.filter(model__icontains=model)
    
    if is_verified is not None:
        queryset = queryset.filter(is_verified=is_verified)
    
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    return queryset.select_related('driver', 'driver__user').prefetch_related('photos')
