"""
Core permissions for DZ Bus Tracker.
"""
from rest_framework import permissions


class BasePermission(permissions.BasePermission):
    """
    Base permission class for DZ Bus Tracker.
    """
    message = "Permission denied."


class IsAdmin(BasePermission):
    """
    Permission to check if user is an admin.
    """
    message = "Only admin users are allowed to perform this action."

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is an admin.
        """
        if not request.user.is_authenticated:
            return False

        return request.user.is_staff or request.user.user_type == "admin"


class IsDriver(BasePermission):
    """
    Permission to check if user is a driver.
    """
    message = "Only drivers are allowed to perform this action."

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is a driver.
        """
        if not request.user.is_authenticated:
            return False

        return request.user.user_type == "driver"


class IsPassenger(BasePermission):
    """
    Permission to check if user is a passenger.
    """
    message = "Only passengers are allowed to perform this action."

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is a passenger.
        """
        if not request.user.is_authenticated:
            return False

        return request.user.user_type == "passenger"


class IsDriverOrAdmin(BasePermission):
    """
    Permission to check if user is a driver or admin.
    """
    message = "Only drivers or admin users are allowed to perform this action."

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is a driver or admin.
        """
        if not request.user.is_authenticated:
            return False

        return (
                request.user.user_type == "driver" or
                request.user.user_type == "admin" or
                request.user.is_staff
        )


class IsOwnerOrReadOnly(BasePermission):
    """
    Permission to check if user is the owner of an object.
    """
    message = "You must be the owner of this object to perform this action."

    def has_object_permission(self, request, view, obj):
        """
        Check if user is the owner of an object or is making a safe request.
        """
        # Always allow GET, HEAD, or OPTIONS requests
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if user is the owner
        if hasattr(obj, "user"):
            return obj.user == request.user
        elif hasattr(obj, "owner"):
            return obj.owner == request.user
        elif hasattr(obj, "driver") and hasattr(obj.driver, "user"):
            return obj.driver.user == request.user
        elif obj.__class__.__name__ == 'User':
            # For User objects, check if it's the same user
            return obj == request.user

        return False


class IsAdminOrReadOnly(BasePermission):
    """
    Permission to check if user is an admin for write operations.
    """
    message = "Only admin users can perform write operations."

    def has_permission(self, request, view):
        """
        Check if user is an admin for write operations.
        """
        # Always allow GET, HEAD, or OPTIONS requests
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if user is staff or admin
        if not request.user.is_authenticated:
            return False

        return request.user.is_staff or request.user.user_type == "admin"


class IsApprovedDriver(BasePermission):
    """
    Permission to check if user is an approved driver.
    """
    message = "You must be an approved driver to perform this action."

    def has_permission(self, request, view):
        """
        Check if user is an approved driver.
        """
        if not request.user.is_authenticated:
            return False

        if request.user.user_type != "driver":
            return False

        # Check if driver profile exists and is approved
        try:
            return (
                    hasattr(request.user, "driver") and
                    request.user.driver.status == "approved"
            )
        except Exception:
            return False
        