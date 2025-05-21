"""
Pagination classes for DZ Bus Tracker API.
"""
from rest_framework.pagination import (
    PageNumberPagination,
    LimitOffsetPagination,
    CursorPagination,
)
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination with 20 items per page.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """
        Return a paginated response with extra metadata.
        """
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data,
        })


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for larger result sets with 50 items per page.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        """
        Return a paginated response with extra metadata.
        """
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data,
        })


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for smaller result sets with 10 items per page.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50

    def get_paginated_response(self, data):
        """
        Return a paginated response with extra metadata.
        """
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data,
        })


class CursorBasedPagination(CursorPagination):
    """
    Cursor-based pagination for high-performance apps.
    More efficient for large datasets but requires an ordering.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'

    def get_paginated_response(self, data):
        """
        Return a paginated response with extra metadata.
        """
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class StandardLimitOffsetPagination(LimitOffsetPagination):
    """
    Limit-offset pagination for flexible paging.
    """
    default_limit = 20
    max_limit = 100

    def get_paginated_response(self, data):
        """
        Return a paginated response with extra metadata.
        """
        return Response({
            'count': self.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })