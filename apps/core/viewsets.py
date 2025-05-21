"""
Core viewsets for DZ Bus Tracker.
"""
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .mixins.views import APILogMixin, MultiSerializerMixin, PermissionsMixin, QuerySetMixin


class BaseModelViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    viewsets.ModelViewSet
):
    """
    Base viewset for model operations with extended functionality.
    """

    def get_serializer_context(self):
        """
        Return the serializer context with additional data.
        """
        context = super().get_serializer_context()
        context["request"] = self.request
        context["view"] = self
        return context


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


class CreateRetrieveViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    Viewset that allows creation and retrieval but not updating or deletion.
    """
    pass


class CreateListRetrieveViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    Viewset that allows creation, listing, and retrieval but not updating or deletion.
    """
    pass


class NoDeleteModelViewSet(
    APILogMixin,
    MultiSerializerMixin,
    PermissionsMixin,
    QuerySetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    Viewset that allows all operations except deletion.
    """
    pass


class NestedModelViewSet(BaseModelViewSet):
    """
    Viewset for nested resources.
    """
    parent_lookup_field = None
    parent_model = None
    parent_queryset = None

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

        return parent_queryset.get(**parent_filter)

    def get_queryset(self):
        """
        Filter queryset based on the parent object.
        """
        queryset = super().get_queryset()
        parent = self.get_parent_object()

        if parent:
            # Determine the foreign key field name
            model_name = self.parent_model.__name__.lower()
            fk_field = f"{model_name}_id"

            # If the model has a different field name for the foreign key,
            # override it in the viewset
            if hasattr(self, "parent_field_name"):
                fk_field = self.parent_field_name

            # Filter queryset
            return queryset.filter(**{fk_field: parent.id})

        return queryset


class SoftDeleteModelViewSet(BaseModelViewSet):
    """
    Viewset that supports soft deletion.
    """

    def perform_destroy(self, instance):
        """
        Soft delete an instance by marking it as deleted.
        """
        if hasattr(instance, "is_deleted"):
            instance.is_deleted = True
            instance.save(update_fields=["is_deleted", "deleted_at"])
        else:
            # Fall back to hard delete if model doesn't support soft delete
            instance.delete()

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """
        Restore a soft-deleted instance.
        """
        instance = self.get_object()

        if not hasattr(instance, "is_deleted"):
            return Response(
                {"detail": _("This resource does not support restoration.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not instance.is_deleted:
            return Response(
                {"detail": _("This resource is not deleted.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.is_deleted = False
        instance.deleted_at = None
        instance.save(update_fields=["is_deleted", "deleted_at"])

        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    