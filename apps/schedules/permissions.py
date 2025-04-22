# apps/schedules/permissions.py
from rest_framework.permissions import BasePermission

class SchedulePermission(BasePermission):
    def has_permission(self, request, view):
        # Allow read-only requests for everyone
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        # Write access requires authentication and a proper user type (admin or driver)
        return request.user.is_authenticated and (request.user.is_staff or request.user.user_type in ['driver', 'admin'])

    def has_object_permission(self, request, view, obj):
        # Allow safe methods for everyone
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        # Admins always pass; drivers can update only their own schedules
        if request.user.is_staff:
            return True
        if hasattr(obj, 'driver') and obj.driver.user == request.user:
            return True
        return False
