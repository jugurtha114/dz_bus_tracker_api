"""
Custom exceptions for DZ Bus Tracker.
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from django.utils.translation import gettext_lazy as _


class ApplicationError(APIException):
    """
    Base exception for application errors.
    """
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _("An unexpected error occurred.")
    default_code = "application_error"


class ValidationError(ApplicationError):
    """
    Exception for validation errors.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("Invalid data provided.")
    default_code = "validation_error"


class ResourceNotFoundError(ApplicationError):
    """
    Exception for resource not found errors.
    """
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("Requested resource not found.")
    default_code = "resource_not_found"


class AuthenticationError(ApplicationError):
    """
    Exception for authentication errors.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _("Authentication failed.")
    default_code = "authentication_error"


class PermissionDeniedError(ApplicationError):
    """
    Exception for permission denied errors.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Permission denied.")
    default_code = "permission_denied"


class ServiceUnavailableError(ApplicationError):
    """
    Exception for service unavailable errors.
    """
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("Service unavailable.")
    default_code = "service_unavailable"


class RateLimitExceededError(ApplicationError):
    """
    Exception for rate limit exceeded errors.
    """
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _("Rate limit exceeded.")
    default_code = "rate_limit_exceeded"


class DriverNotApprovedError(ApplicationError):
    """
    Exception for driver not approved errors.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Driver not approved.")
    default_code = "driver_not_approved"


class BusTrackingError(ApplicationError):
    """
    Exception for bus tracking errors.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("Bus tracking error.")
    default_code = "bus_tracking_error"
