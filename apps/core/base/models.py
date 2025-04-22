import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    Base model with created and updated timestamps.
    """
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True,
    )

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Base model with UUID as primary key.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        abstract = True


class IsActiveModel(models.Model):
    """
    Base model with is_active flag.
    """
    is_active = models.BooleanField(
        _('Active'),
        default=True,
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    Base model with soft delete functionality.
    """
    is_deleted = models.BooleanField(
        _('Deleted'),
        default=False,
    )
    deleted_at = models.DateTimeField(
        _('Deleted at'),
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Soft delete the instance.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """
        Permanently delete the instance.
        """
        return super().delete(using, keep_parents)


class GeoPointModel(models.Model):
    """
    Base model with latitude and longitude fields.
    """
    latitude = models.DecimalField(
        _('Latitude'),
        max_digits=9,
        decimal_places=6,
    )
    longitude = models.DecimalField(
        _('Longitude'),
        max_digits=9,
        decimal_places=6,
    )
    accuracy = models.FloatField(
        _('Accuracy (meters)'),
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    @property
    def coordinates(self):
        """
        Return coordinates as (latitude, longitude) tuple.
        """
        return (float(self.latitude), float(self.longitude))

    @coordinates.setter
    def coordinates(self, coords):
        """
        Set coordinates from (latitude, longitude) tuple.
        """
        self.latitude, self.longitude = coords


class BaseModel(UUIDModel, TimeStampedModel, IsActiveModel, SoftDeleteModel):
    """
    Complete base model with all base functionality.
    """
    class Meta:
        abstract = True
