# apps/notifications/permissions.py
from rest_framework import permissions
from .models import Notification, NotificationPreference

class NotificationPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, (Notification, NotificationPreference)):
            return obj.user == request.user
        return False