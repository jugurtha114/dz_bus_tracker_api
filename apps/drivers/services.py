from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from apps.core.exceptions import ValidationError, ObjectNotFound
from apps.notifications.services import send_notification
from .models import Driver, DriverApplication, DriverRating


def create_driver(user, data):
    with transaction.atomic():
        # Create the driver
        driver = Driver.objects.create(
            user=user,
            id_number=data.get('id_number'),
            id_photo=data.get('id_photo'),
            license_number=data.get('license_number'),
            license_photo=data.get('license_photo'),
            experience_years=data.get('experience_years', 0),
            date_of_birth=data.get('date_of_birth'),
            address=data.get('address', ''),
            emergency_contact=data.get('emergency_contact', ''),
            notes=data.get('notes', ''),
            metadata=data.get('metadata', {}),
        )
        
        # Create initial application
        DriverApplication.objects.create(
            driver=driver,
            status='pending',
            notes=data.get('application_notes', ''),
            metadata=data.get('application_metadata', {}),
        )
        
        # Notify admin of new driver application
        notify_admins_new_driver(driver)
        
        # Update user type
        user.user_type = 'driver'
        user.save(update_fields=['user_type'])
        
        return driver


def update_driver(driver_id, data):
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        raise ObjectNotFound("Driver not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(driver, field):
            setattr(driver, field, value)
    
    driver.save()
    
    # Invalidate cache
    cache_key = f'driver:{driver_id}'
    cache.delete(cache_key)
    
    return driver


def verify_driver(application_id, admin_user, status, notes='', rejection_reason=''):
    try:
        application = DriverApplication.objects.get(id=application_id)
    except DriverApplication.DoesNotExist:
        raise ObjectNotFound("Driver application not found")
    
    # Validate status
    if status not in ['approved', 'rejected']:
        raise ValidationError("Invalid status")
    
    # If rejecting, rejection reason is required
    if status == 'rejected' and not rejection_reason:
        raise ValidationError("Rejection reason is required when rejecting an application")
    
    # Update the application
    application.status = status
    application.reviewed_by = admin_user
    application.reviewed_at = timezone.now()
    application.notes = notes
    application.rejection_reason = rejection_reason
    application.save()
    
    # Notify driver
    notify_driver_verification(application.driver, status, rejection_reason)
    
    return application


def create_driver_rating(passenger, driver_id, rating_data):
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        raise ObjectNotFound("Driver not found")
    
    # Check if user has already rated this driver for this trip
    trip = rating_data.get('trip')
    if trip and DriverRating.objects.filter(
        driver=driver,
        passenger=passenger,
        trip=trip
    ).exists():
        raise ValidationError("You have already rated this driver for this trip")
    
    # Create the rating
    rating = DriverRating.objects.create(
        driver=driver,
        passenger=passenger,
        rating=rating_data.get('rating'),
        comment=rating_data.get('comment', ''),
        trip=trip,
        is_anonymous=rating_data.get('is_anonymous', False),
    )
    
    # Notify driver of new rating
    notify_driver_new_rating(driver, rating)
    
    return rating


def deactivate_driver(driver_id, reason=''):
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        raise ObjectNotFound("Driver not found")
    
    # Check if driver has active tracking sessions
    if driver.has_active_tracking:
        active_session = driver.active_tracking_session
        if active_session:
            from apps.tracking.services import end_tracking_session
            end_tracking_session(active_session.id)
    
    # Deactivate driver
    driver.is_active = False
    driver.save()
    
    # Deactivate user account
    driver.user.is_active = False
    driver.user.save()
    
    return driver


def reactivate_driver(driver_id):
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        raise ObjectNotFound("Driver not found")
    
    # Reactivate driver
    driver.is_active = True
    driver.save()
    
    # Reactivate user account
    driver.user.is_active = True
    driver.user.save()
    
    return driver


def notify_admins_new_driver(driver):
    from apps.authentication.selectors import get_active_admins
    
    admin_users = get_active_admins()
    
    for admin in admin_users:
        send_notification(
            user=admin,
            notification_type='system',
            title='New Driver Application',
            message=f'A new driver has applied: {driver.full_name} ({driver.id_number})',
            data={
                'driver_id': str(driver.id),
                'action': 'verify_driver'
            }
        )


def notify_driver_verification(driver, status, rejection_reason=''):
    if status == 'approved':
        send_notification(
            user=driver.user,
            notification_type='verification',
            title='Driver Application Approved',
            message='Your driver application has been approved. You can now add buses and start tracking.',
            data={
                'status': status
            }
        )
    else:
        send_notification(
            user=driver.user,
            notification_type='verification',
            title='Driver Application Rejected',
            message=f'Your driver application has been rejected: {rejection_reason}',
            data={
                'status': status,
                'reason': rejection_reason
            }
        )


def notify_driver_new_rating(driver, rating):
    if not rating.is_anonymous:
        passenger_name = rating.passenger.get_full_name()
    else:
        passenger_name = "Anonymous"
    
    send_notification(
        user=driver.user,
        notification_type='system',
        title='New Rating Received',
        message=f'You received a {rating.rating}-star rating from {passenger_name}',
        data={
            'rating_id': str(rating.id),
            'rating': rating.rating
        }
    )


def get_driver_stats(driver_id):
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        raise ObjectNotFound("Driver not found")
    
    from django.db.models import Sum, Avg, Count
    from django.utils import timezone
    from datetime import timedelta
    
    # Get all tracking sessions
    from apps.tracking.models import TrackingSession
    sessions = TrackingSession.objects.filter(driver=driver)
    
    # Total trips
    total_trips = sessions.count()
    
    # Total distance
    total_distance = sessions.aggregate(Sum('total_distance'))['total_distance__sum'] or 0
    
    # Active since
    active_since = driver.created_at
    
    # Bus count
    from apps.buses.models import Bus
    bus_count = Bus.objects.filter(driver=driver).count()
    
    # Verified bus count
    verified_bus_count = Bus.objects.filter(driver=driver, is_verified=True).count()
    
    # Average rating
    average_rating = DriverRating.objects.filter(driver=driver).aggregate(
        Avg('rating')
    )['rating__avg'] or 0
    
    # Total ratings
    total_ratings = DriverRating.objects.filter(driver=driver).count()
    
    # Completed trips last month
    last_month = timezone.now() - timedelta(days=30)
    completed_trips_last_month = sessions.filter(
        end_time__gte=last_month,
        status='completed'
    ).count()
    
    return {
        'total_trips': total_trips,
        'total_distance': total_distance,
        'active_since': active_since,
        'bus_count': bus_count,
        'verified_bus_count': verified_bus_count,
        'average_rating': average_rating,
        'total_ratings': total_ratings,
        'completed_trips_last_month': completed_trips_last_month
    }