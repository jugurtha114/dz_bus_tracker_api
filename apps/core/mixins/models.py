"""
Model mixins for reuse across the application.
"""
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedMixin(models.Model):
    """
    Adds created and updated timestamps to models.
    """
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class UUIDMixin(models.Model):
    """
    Adds a UUID primary key to models.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("ID"),
    )

    class Meta:
        abstract = True


class StatusMixin(models.Model):
    """
    Adds a status field to models.
    """
    status = models.CharField(
        _("status"),
        max_length=50,
        db_index=True,
    )
    status_changed_at = models.DateTimeField(
        _("status changed at"),
        default=timezone.now,
        db_index=True,
    )

    def save(self, *args, **kwargs):
        """
        Update status_changed_at when status changes.
        """
        if self.pk:
            original = self.__class__.objects.get(pk=self.pk)
            if original.status != self.status:
                self.status_changed_at = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class SoftDeleteMixin(models.Model):
    """
    Adds soft delete capability to models.
    """
    is_deleted = models.BooleanField(_("deleted"), default=False, db_index=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    def delete(self, using=None, keep_parents=False):
        """
        Soft delete the instance.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def hard_delete(self):
        """
        Permanently delete the instance.
        """
        super().delete()

    class Meta:
        abstract = True


class ActiveMixin(models.Model):
    """
    Adds an active field to models.
    """
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        abstract = True


class SlugMixin(models.Model):
    """
    Adds a slug field to models.
    """
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)

    class Meta:
        abstract = True


class GeoLocationMixin(models.Model):
    """
    Adds latitude and longitude fields to models.
    """
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
        help_text=_("Latitude in decimal degrees"),
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
        help_text=_("Longitude in decimal degrees"),
    )

    class Meta:
        abstract = True
        