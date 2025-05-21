"""
Exception handling for DZ Bus Tracker API.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError as AppValidationError,
)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for API views.

    Returns a response with standardized error format.
    """
    # First, get the standard DRF response
    response = exception_handler(exc, context)

    # If this is already handled by DRF, just return it
    if response is not None:
        # Standardize the response format
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                # Keep the detail as is
                pass
            elif 'non_field_errors' in response.data:
                # Non-field errors become the detail
                response.data = {
                    'detail': response.data['non_field_errors'][0],
                    'errors': response.data,
                }
            else:
                # Field errors are kept in the errors field
                response.data = {
                    'detail': 'Validation Error',
                    'errors': response.data,
                }
        return response

    # Handle Django exceptions
    if isinstance(exc, Http404):
        response_data = {
            'detail': 'Not found',
        }
        return Response(response_data, status=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, PermissionDenied):
        response_data = {
            'detail': 'Permission denied',
        }
        return Response(response_data, status=status.HTTP_403_FORBIDDEN)

    if isinstance(exc, ValidationError):
        if hasattr(exc, 'message_dict'):
            response_data = {
                'detail': 'Validation Error',
                'errors': exc.message_dict,
            }
        else:
            response_data = {
                'detail': 'Validation Error',
                'errors': {'non_field_errors': exc.messages},
            }
        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    # Handle application-specific exceptions
    if isinstance(exc, ApplicationError):
        response_data = {
            'detail': str(exc),
            'code': getattr(exc, 'default_code', 'application_error'),
        }
        return Response(response_data, status=exc.status_code)

    if isinstance(exc, ResourceNotFoundError):
        response_data = {
            'detail': str(exc),
            'code': 'not_found',
        }
        return Response(response_data, status=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, AuthenticationError):
        response_data = {
            'detail': str(exc),
            'code': 'authentication_error',
        }
        return Response(response_data, status=status.HTTP_401_UNAUTHORIZED)

    if isinstance(exc, PermissionDeniedError):
        response_data = {
            'detail': str(exc),
            'code': 'permission_denied',
        }
        return Response(response_data, status=status.HTTP_403_FORBIDDEN)

    if isinstance(exc, AppValidationError):
        response_data = {
            'detail': str(exc),
            'code': 'validation_error',
        }
        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    # If it's an unknown exception, return 500
    response_data = {
        'detail': 'Server error',
    }
    return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)