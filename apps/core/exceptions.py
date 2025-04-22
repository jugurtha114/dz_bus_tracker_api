from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status
from django.utils.translation import gettext_lazy as _


class BaseAPIException(APIException):
    """Base exception for custom API exceptions."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('A server error occurred.')
    default_code = 'error'


class ValidationError(BaseAPIException):
    """Exception raised for validation errors."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid input.')
    default_code = 'invalid'


class PermissionDenied(BaseAPIException):
    """Exception raised for permission errors."""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _('You do not have permission to perform this action.')
    default_code = 'permission_denied'


class ObjectNotFound(BaseAPIException):
    """Exception raised for not found errors."""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('Object not found.')
    default_code = 'not_found'


class ServiceUnavailable(BaseAPIException):
    """Exception raised for service unavailability."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _('Service temporarily unavailable.')
    default_code = 'service_unavailable'


class InvalidCredentials(BaseAPIException):
    """Exception raised for invalid credentials."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _('Invalid credentials.')
    default_code = 'invalid_credentials'


class InvalidVerificationStatus(BaseAPIException):
    """Exception raised for invalid verification status."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid verification status.')
    default_code = 'invalid_verification_status'


class InvalidTrackingSession(BaseAPIException):
    """Exception raised for invalid tracking session."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid tracking session.')
    default_code = 'invalid_tracking_session'


class InvalidLocationData(BaseAPIException):
    """Exception raised for invalid location data."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid location data.')
    default_code = 'invalid_location_data'


class RateLimitExceeded(BaseAPIException):
    """Exception raised for rate limit exceeded."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _('Rate limit exceeded.')
    default_code = 'rate_limit_exceeded'


def custom_exception_handler(exc, context):
    """
    Custom exception handler for API views.
    
    Args:
        exc: The exception
        context: The exception context
        
    Returns:
        Response object
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # If response is None, create a default one
    if response is None:
        return response
    
    # Add more detail to the response
    if hasattr(exc, 'default_code'):
        code = exc.default_code
    elif hasattr(exc, 'code'):
        code = exc.code
    else:
        code = 'error'
    
    response.data = {
        'status': 'error',
        'code': code,
        'message': str(exc),
        'details': response.data if isinstance(response.data, dict) else {'detail': response.data},
    }
    
    return response
