from rest_framework import status, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework.pagination import PageNumberPagination

from utils.cache import cache_drf_response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination settings for API views.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class OptimizedPagination(PageNumberPagination):
    """
    Pagination with performance optimizations for large datasets.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'page': self.page.number,
            'pages': self.page.paginator.num_pages,
            'page_size': self.get_page_size(self.request),
            'results': data
        })


class BaseAPIView(APIView):
    """
    Base API view with common functionality.
    """
    def get_serializer_context(self):
        return {'request': self.request}
    
    def get_serializer_class(self):
        assert self.serializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method."
            % self.__class__.__name__
        )
        return self.serializer_class
    
    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, **kwargs)


class BaseViewSet(ModelViewSet):
    """
    Base view set with common functionality.
    """
    pagination_class = StandardResultsSetPagination
    
    def get_serializer_context(self):
        return {'request': self.request}
    
    @cache_drf_response(timeout=300)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @cache_drf_response(timeout=300)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class ReadOnlyViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    A viewset that provides default `retrieve()` and `list()` actions.
    """
    pagination_class = StandardResultsSetPagination
    
    @cache_drf_response(timeout=300)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @cache_drf_response(timeout=300)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class CreateListRetrieveViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    A viewset that provides `create()`, `retrieve()`, and `list()` actions.
    """
    pagination_class = StandardResultsSetPagination
    
    @cache_drf_response(timeout=300)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @cache_drf_response(timeout=300)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class NoDeleteViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    A viewset that excludes the delete operation.
    """
    pagination_class = StandardResultsSetPagination
    
    @cache_drf_response(timeout=300)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @cache_drf_response(timeout=300)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class BulkCreateMixin:
    """
    Mixin for bulk creation of objects.
    """
    def create_bulk(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_bulk_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def perform_bulk_create(self, serializer):
        serializer.save()


class OptimizedFilterMixin:
    """
    Mixin for optimized filtering in list views.
    """
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply select_related and prefetch_related if defined
        if hasattr(self, 'select_related_fields'):
            queryset = queryset.select_related(*self.select_related_fields)
        
        if hasattr(self, 'prefetch_related_fields'):
            queryset = queryset.prefetch_related(*self.prefetch_related_fields)
        
        return queryset
