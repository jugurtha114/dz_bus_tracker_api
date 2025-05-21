"""
Pagination utilities for DZ Bus Tracker.
"""
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for DZ Bus Tracker.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for smaller result sets.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for larger result sets.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


def paginate_queryset(queryset, request, page_size=20):
    """
    Paginate a queryset and return paginated data.

    Args:
        queryset: Django queryset to paginate
        request: Request object containing pagination parameters
        page_size: Number of items per page

    Returns:
        Dict containing paginated data and pagination metadata
    """
    page = request.query_params.get('page', 1)
    try:
        page_number = int(page)
    except (TypeError, ValueError):
        page_number = 1

    # Get page size from query params or use default
    try:
        size = int(request.query_params.get('page_size', page_size))
        # Cap page size
        page_size = min(size, 100)
    except (TypeError, ValueError):
        pass

    paginator = Paginator(queryset, page_size)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return {
        'count': paginator.count,
        'num_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'results': page_obj.object_list,
    }


def get_paginated_response(data, request, page_size=20):
    """
    Get a paginated response for a queryset.

    Args:
        data: Django queryset to paginate
        request: Request object containing pagination parameters
        page_size: Number of items per page

    Returns:
        DRF Response object with paginated data
    """
    paginated_data = paginate_queryset(data, request, page_size)
    return Response(paginated_data)