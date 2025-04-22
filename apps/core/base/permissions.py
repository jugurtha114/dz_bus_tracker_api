from rest_framework import permissions
from django.utils.translation import gettext_lazy as _

class IsAdmin(permissions.BasePermission):
    """
    Permission to only allow admin users.
    """
    message = _('You do not have admin privileges to perform this action.')

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'admin'


class IsDriver(permissions.BasePermission):
    """
    Permission to only allow driver users.
    """
    message = _('You do not have driver privileges to perform this action.')

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'driver'


class IsPassenger(permissions.BasePermission):
    """
    Permission to only allow passenger users.
    """
    message = _('You do not have passenger privileges to perform this action.')

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'passenger'


class IsAdminOrDriver(permissions.BasePermission):
    """
    Permission to allow admin or driver users.
    """
    message = _('You must be an admin or driver to perform this action.')

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['admin', 'driver']


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission to allow only admin users to perform write operations.
    """
    message = _('You do not have admin privileges to perform this action.')

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.user_type == 'admin'


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to allow only owners or admins to access objects.
    """
    message = _('You do not have permission to perform this action.')

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
            
        # Admin can do anything
        if request.user.user_type == 'admin':
            return True
            
        # Check if the user is the owner
        if hasattr(obj, 'user_id'):
            return obj.user_id == request.user.id
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'driver') and hasattr(obj.driver, 'user'):
            return obj.driver.user == request.user
        elif hasattr(obj, 'passenger') and hasattr(obj.passenger, 'user'):
            return obj.passenger.user == request.user
            
        return False


class IsDriverWithVerifiedBus(permissions.BasePermission):
    """
    Permission to allow only drivers with verified buses.
    """
    message = _('You must be a driver with at least one verified bus to perform this action.')

    def has_permission(self, request, view):
        if not request.user.is_authenticated or request.user.user_type != 'driver':
            return False
            
        # Check if the driver has at least one verified bus
        try:
            from apps.drivers.models import Driver
            from apps.buses.models import Bus
            
            driver = Driver.objects.filter(
                user=request.user, 
                is_active=True, 
                is_verified=True
            ).first()
            
            if not driver:
                return False
                
            verified_bus_exists = Bus.objects.filter(
                driver=driver,
                is_active=True,
                is_verified=True
            ).exists()
            
            return verified_bus_exists
        except:
            return False


class IsVerifiedDriver(permissions.BasePermission):
    """
    Permission to allow only verified drivers.
    """
    message = _('You must be a verified driver to perform this action.')

    def has_permission(self, request, view):
        if not request.user.is_authenticated or request.user.user_type != 'driver':
            return False
            
        # Check if the driver is verified
        try:
            from apps.drivers.models import Driver
            
            driver = Driver.objects.filter(
                user=request.user, 
                is_active=True, 
                is_verified=True
            ).exists()
            
            return driver
        except:
            return False


class ReadOnly(permissions.BasePermission):
    """
    Permission to only allow read-only operations.
    """
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS
