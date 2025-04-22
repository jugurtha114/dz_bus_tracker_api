from django.db.models import Q, Avg, Count, Prefetch
from django.core.cache import cache

from utils.cache import cached_result
from .models import Driver, DriverApplication, DriverRating


@cached_result('driver', timeout=60)
def get_driver_by_id(driver_id):
    try:
        return Driver.objects.select_related(
            'user'
        ).prefetch_related(
            'ratings', 'buses'
        ).get(id=driver_id)
    except Driver.DoesNotExist:
        return None


def get_driver_by_id_number(id_number):
    try:
        return Driver.objects.select_related('user').get(id_number=id_number)
    except Driver.DoesNotExist:
        return None


def get_driver_by_license(license_number):
    try:
        return Driver.objects.select_related('user').get(license_number=license_number)
    except Driver.DoesNotExist:
        return None


def get_driver_for_user(user):
    try:
        return Driver.objects.select_related('user').get(user=user)
    except Driver.DoesNotExist:
        return None


def get_active_drivers():
    return Driver.objects.filter(
        is_active=True, 
        is_verified=True
    ).select_related('user')


def get_drivers_by_verification_status(status):
    # Get the latest application for each driver
    latest_applications = DriverApplication.objects.filter(
        status=status
    ).values('driver').annotate(
        latest_id=Count('id')
    ).values('driver')
    
    # Get drivers with latest application having the specified status
    return Driver.objects.filter(
        id__in=latest_applications
    ).select_related('user').prefetch_related(
        Prefetch(
            'applications',
            queryset=DriverApplication.objects.filter(status=status).order_by('-created_at'),
            to_attr='latest_applications'
        )
    )


def get_drivers_with_buses():
    return Driver.objects.filter(
        buses__isnull=False
    ).distinct().select_related('user').prefetch_related('buses')


def get_drivers_with_verified_buses():
    return Driver.objects.filter(
        buses__is_verified=True
    ).distinct().select_related('user').prefetch_related(
        Prefetch(
            'buses',
            queryset=Bus.objects.filter(is_verified=True),
            to_attr='verified_buses'
        )
    )


def get_driver_ratings(driver_id, anonymous_only=False):
    queryset = DriverRating.objects.filter(driver_id=driver_id)
    
    if anonymous_only:
        queryset = queryset.filter(is_anonymous=True)
    
    return queryset.select_related('passenger')


def get_driver_average_rating(driver_id):
    avg_rating = DriverRating.objects.filter(
        driver_id=driver_id
    ).aggregate(Avg('rating'))['rating__avg']
    
    return avg_rating or 0


def get_top_rated_drivers(limit=10):
    return Driver.objects.annotate(
        avg_rating=Avg('ratings__rating'),
        rating_count=Count('ratings')
    ).filter(
        is_active=True,
        is_verified=True,
        rating_count__gt=0
    ).order_by('-avg_rating', '-rating_count')[:limit]


def filter_drivers(query=None, verification_status=None, is_active=None, has_buses=None):
    queryset = Driver.objects.all()
    
    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query) | 
            Q(user__last_name__icontains=query) | 
            Q(id_number__icontains=query) |
            Q(license_number__icontains=query)
        )
    
    if verification_status:
        queryset = queryset.filter(is_verified=(verification_status.lower() == 'verified'))
    
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    if has_buses is not None:
        if has_buses:
            queryset = queryset.filter(buses__isnull=False).distinct()
        else:
            queryset = queryset.filter(buses__isnull=True)
    
    return queryset.select_related('user')


def get_drivers_by_application_date(start_date=None, end_date=None):
    queryset = Driver.objects.all()
    
    if start_date:
        queryset = queryset.filter(created_at__gte=start_date)
    
    if end_date:
        queryset = queryset.filter(created_at__lte=end_date)
    
    return queryset.select_related('user').order_by('-created_at')
