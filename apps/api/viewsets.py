"""
Base viewsets for DZ Bus Tracker API.
"""
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins.views import (
    APILogMixin,
    CacheMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
)


class BaseModelViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    viewsets.ModelViewSet
):
    """
    Base viewset for model operations with extended functionality.
    Only supports PATCH for updates, not PUT.
    """
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options', 'trace']

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        context = super().get_serializer_context()
        context.update({
            'request': self.request,
            'view': self,
            'action': self.action,
        })
        return context

    def get_queryset(self):
        """
        Get the list of items for this view with request filtering.
        """
        queryset = super().get_queryset()

        # Apply custom filtering based on request
        if hasattr(self, 'filter_queryset_by_request'):
            queryset = self.filter_queryset_by_request(queryset)

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Create a model instance using a service if available.
        """
        if hasattr(self, 'service_class') and hasattr(self.service_class, 'create'):
            # Extract data from serializer
            data = serializer.validated_data

            # Call service to create object
            instance = self.service_class.create(**data)

            # Update serializer instance
            serializer.instance = instance
        else:
            # Default behavior
            super().perform_create(serializer)

    @transaction.atomic
    def perform_update(self, serializer):
        """
        Update a model instance using a service if available.
        """
        if hasattr(self, 'service_class') and hasattr(self.service_class, 'update'):
            # Extract data from serializer
            data = serializer.validated_data

            # Call service to update object
            instance = self.service_class.update(serializer.instance.id, **data)

            # Update serializer instance
            serializer.instance = instance
        else:
            # Default behavior
            super().perform_update(serializer)

    @transaction.atomic
    def perform_destroy(self, instance):
        """
        Delete a model instance using a service if available.
        """
        if hasattr(self, 'service_class') and hasattr(self.service_class, 'delete'):
            # Call service to delete object
            self.service_class.delete(instance.id)
        else:
            # Default behavior
            super().perform_destroy(instance)


class ReadOnlyModelViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    viewsets.ReadOnlyModelViewSet
):
    """
    Base viewset for read-only operations.
    """
    pass


class CachedReadOnlyModelViewSet(
    CacheMixin,
    ReadOnlyModelViewSet
):
    """
    Read-only viewset with response caching.
    """
    pass


class NestedModelViewSet(BaseModelViewSet):
    """
    Viewset for nested resources.
    """
    parent_lookup_field = None
    parent_model = None
    parent_queryset = None
    parent_field_name = None

    def get_parent_object(self):
        """
        Get the parent object based on the URL parameters.
        """
        if not self.parent_lookup_field or not self.parent_model:
            return None

        parent_lookup_value = self.kwargs.get(f"parent_{self.parent_lookup_field}")

        if not parent_lookup_value:
            return None

        parent_queryset = self.parent_queryset or self.parent_model.objects.all()
        parent_filter = {self.parent_lookup_field: parent_lookup_value}

        try:
            return parent_queryset.get(**parent_filter)
        except self.parent_model.DoesNotExist:
            return None

    def get_queryset(self):
        """
        Filter queryset based on the parent object.
        """
        queryset = super().get_queryset()
        parent = self.get_parent_object()

        if parent:
            # Determine the foreign key field name
            fk_field = self.parent_field_name

            if not fk_field:
                model_name = self.parent_model.__name__.lower()
                fk_field = f"{model_name}_id"

            # Filter queryset
            return queryset.filter(**{fk_field: parent.id})

        return queryset

    def perform_create(self, serializer):
        """
        Create a model instance with parent relation.
        """
        parent = self.get_parent_object()

        if parent:
            # Determine the foreign key field name
            fk_field = self.parent_field_name

            if not fk_field:
                model_name = self.parent_model.__name__.lower()
                fk_field = model_name

            # Add parent to serializer
            serializer.save(**{fk_field: parent})
        else:
            super().perform_create(serializer)


class BatchOperationViewSet(BaseModelViewSet):
    """
    Viewset with support for batch operations.
    """

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple resources in a single request.
        """
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_bulk_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_bulk_create(self, serializer):
        """
        Create multiple model instances.
        """
        serializer.save()

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        """
        Update multiple resources in a single request.
        """
        # Extract object IDs
        if not isinstance(request.data, list):
            return Response(
                {"detail": "Expected a list of items"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get objects to update
        ids = [item.get('id') for item in request.data if 'id' in item]
        objects = self.get_queryset().filter(id__in=ids)

        # Map objects by ID
        id_to_obj = {str(obj.id): obj for obj in objects}

        # Update objects
        updates = []
        for item in request.data:
            obj_id = item.get('id')
            if not obj_id or obj_id not in id_to_obj:
                continue

            obj = id_to_obj[obj_id]
            serializer = self.get_serializer(obj, data=item, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            updates.append(serializer.data)

        return Response(updates)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """
        Delete multiple resources in a single request.
        """
        # Extract object IDs
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {"detail": "No IDs provided for deletion"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get objects to delete
        objects = self.get_queryset().filter(id__in=ids)

        # Delete objects
        deleted_count = objects.count()
        self.perform_bulk_delete(objects)

        return Response(
            {"detail": f"Deleted {deleted_count} objects"},
            status=status.HTTP_204_NO_CONTENT
        )

    def perform_bulk_delete(self, queryset):
        """
        Delete multiple model instances.
        """
        queryset.delete()