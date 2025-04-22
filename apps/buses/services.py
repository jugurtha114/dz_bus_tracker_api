from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

from apps.core.exceptions import ValidationError, ObjectNotFound
from apps.notifications.services import send_notification
from .models import Bus, BusPhoto, BusVerification, BusMaintenance


def create_bus(driver, data, photos=None, photo_types=None):
    with transaction.atomic():
        # Create the bus
        bus = Bus.objects.create(
            driver=driver,
            matricule=data.get('matricule'),
            brand=data.get('brand'),
            model=data.get('model'),
            year=data.get('year'),
            capacity=data.get('capacity', 0),
            description=data.get('description', ''),
            metadata=data.get('metadata', {}),
        )
        
        # Create photos if provided
        if photos and photo_types and len(photos) == len(photo_types):
            for photo, photo_type in zip(photos, photo_types):
                BusPhoto.objects.create(
                    bus=bus,
                    photo=photo,
                    photo_type=photo_type
                )
        
        # Create initial verification record
        BusVerification.objects.create(
            bus=bus,
            status='pending'
        )
        
        # Notify admin of new bus registration
        notify_admins_new_bus(bus)
        
        return bus


def update_bus(bus_id, data):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Update fields
    for field, value in data.items():
        if hasattr(bus, field):
            setattr(bus, field, value)
    
    bus.save()
    
    # Invalidate cache
    cache_key = f'bus:{bus_id}'
    cache.delete(cache_key)
    
    return bus


def add_bus_photo(bus_id, photo, photo_type, description=''):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Create photo
    bus_photo = BusPhoto.objects.create(
        bus=bus,
        photo=photo,
        photo_type=photo_type,
        description=description
    )
    
    return bus_photo


def verify_bus(bus_id, admin_user, status, notes='', rejection_reason=''):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Validate status
    if status not in ['approved', 'rejected']:
        raise ValidationError("Invalid status")
    
    # If rejecting, rejection reason is required
    if status == 'rejected' and not rejection_reason:
        raise ValidationError("Rejection reason is required when rejecting a bus")
    
    # Create verification record
    verification = BusVerification.objects.create(
        bus=bus,
        verified_by=admin_user,
        status=status,
        verification_date=timezone.now(),
        rejection_reason=rejection_reason,
        notes=notes
    )
    
    # Update bus verification status
    bus.is_verified = (status == 'approved')
    bus.verification_date = timezone.now() if status == 'approved' else None
    bus.save()
    
    # Notify driver
    notify_driver_bus_verification(bus, status, rejection_reason)
    
    return verification


def add_maintenance_record(bus_id, data):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Create maintenance record
    maintenance = BusMaintenance.objects.create(
        bus=bus,
        maintenance_type=data.get('maintenance_type'),
        date=data.get('date'),
        description=data.get('description'),
        cost=data.get('cost'),
        performed_by=data.get('performed_by', ''),
        notes=data.get('notes', '')
    )
    
    # Update bus last maintenance date if this is newer
    if not bus.last_maintenance or maintenance.date > bus.last_maintenance:
        bus.last_maintenance = maintenance.date
        bus.save(update_fields=['last_maintenance'])
    
    return maintenance


def deactivate_bus(bus_id, reason=''):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Check if bus is currently tracking
    if bus.is_tracking:
        active_session = bus.current_tracking_session
        if active_session:
            from apps.tracking.services import end_tracking_session
            end_tracking_session(active_session.id)
    
    # Deactivate bus
    bus.is_active = False
    bus.save()
    
    return bus


def reactivate_bus(bus_id):
    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Reactivate bus
    bus.is_active = True
    bus.save()
    
    return bus


def notify_admins_new_bus(bus):
    from apps.authentication.selectors import get_active_admins
    
    admin_users = get_active_admins()
    
    for admin in admin_users:
        send_notification(
            user=admin,
            notification_type='system',
            title='New Bus Registration',
            message=f'A new bus has been registered: {bus.matricule} by {bus.driver.user.get_full_name()}',
            data={
                'bus_id': str(bus.id),
                'driver_id': str(bus.driver.id),
                'action': 'verify_bus'
            }
        )


def notify_driver_bus_verification(bus, status, rejection_reason=''):
    driver_user = bus.driver.user
    
    if status == 'approved':
        send_notification(
            user=driver_user,
            notification_type='verification',
            title='Bus Verified',
            message=f'Your bus {bus.matricule} has been verified and approved.',
            data={
                'bus_id': str(bus.id),
                'status': status
            }
        )
    else:
        send_notification(
            user=driver_user,
            notification_type='verification',
            title='Bus Verification Failed',
            message=f'Your bus {bus.matricule} verification has been rejected: {rejection_reason}',
            data={
                'bus_id': str(bus.id),
                'status': status,
                'reason': rejection_reason
            }
        )


def get_bus_status(bus_id):
    try:
        bus = Bus.objects.select_related('driver__user').get(id=bus_id)
    except Bus.DoesNotExist:
        raise ObjectNotFound("Bus not found")
    
    # Check if bus is tracking
    is_tracking = bus.is_tracking
    active_session = bus.current_tracking_session if is_tracking else None
    
    # Get line if tracking
    line_id = None
    line_name = None
    last_update = None
    
    if active_session:
        line_id = active_session.line.id
        line_name = active_session.line.name
        last_update = active_session.last_update
    
    # Build status data
    status_data = {
        'bus_id': str(bus.id),
        'matricule': bus.matricule,
        'status': 'active' if bus.is_active else 'inactive',
        'driver_id': str(bus.driver.id),
        'driver_name': bus.driver.user.get_full_name(),
        'line_id': str(line_id) if line_id else None,
        'line_name': line_name,
        'is_tracking': is_tracking,
        'last_update': last_update
    }
    
    return status_data
