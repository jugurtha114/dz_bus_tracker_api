from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel
from apps.core.constants import APPLICATION_STATUSES, APPLICATION_STATUS_PENDING


class Bus(BaseModel):
    """
    Model for buses.
    """
    driver = models.ForeignKey(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name='buses',
        verbose_name=_('driver'),
    )
    
    matricule = models.CharField(
        _('matricule'),
        max_length=20,
        unique=True,
    )
    
    brand = models.CharField(
        _('brand'),
        max_length=50,
    )
    
    model = models.CharField(
        _('model'),
        max_length=50,
    )
    
    year = models.PositiveIntegerField(
        _('year'),
        null=True,
        blank=True,
    )
    
    capacity = models.PositiveIntegerField(
        _('capacity'),
        default=0,
    )
    
    description = models.TextField(
        _('description'),
        blank=True,
    )
    
    is_verified = models.BooleanField(
        _('verified'),
        default=False,
    )
    
    verification_date = models.DateTimeField(
        _('verification date'),
        null=True,
        blank=True,
    )
    
    last_maintenance = models.DateTimeField(
        _('last maintenance'),
        null=True,
        blank=True,
    )
    
    next_maintenance = models.DateTimeField(
        _('next maintenance'),
        null=True,
        blank=True,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('bus')
        verbose_name_plural = _('buses')
        ordering = ['matricule']
        indexes = [
            models.Index(fields=['driver']),
            models.Index(fields=['matricule']),
            models.Index(fields=['is_verified']),
        ]
    
    def __str__(self):
        return f"{self.matricule} ({self.brand} {self.model})"
    
    @property
    def is_tracking(self):
        """
        Check if the bus is currently being tracked.
        """
        return self.tracking_sessions.filter(status='active').exists()
    
    @property
    def current_tracking_session(self):
        """
        Get the current tracking session for the bus.
        """
        return self.tracking_sessions.filter(status='active').first()


class BusPhoto(BaseModel):
    """
    Model for bus photos.
    """
    bus = models.ForeignKey(
        'Bus',
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name=_('bus'),
    )
    
    photo = models.ImageField(
        _('photo'),
        upload_to='bus_photos/',
    )
    
    photo_type = models.CharField(
        _('photo type'),
        max_length=50,
        choices=(
            ('exterior', _('Exterior')),
            ('interior', _('Interior')),
            ('document', _('Document')),
            ('other', _('Other')),
        ),
        default='exterior',
    )
    
    description = models.CharField(
        _('description'),
        max_length=255,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('bus photo')
        verbose_name_plural = _('bus photos')
        ordering = ['bus', 'photo_type']
    
    def __str__(self):
        return f"{self.bus.matricule} - {self.get_photo_type_display()}"


class BusVerification(BaseModel):
    """
    Model for bus verification.
    """
    bus = models.ForeignKey(
        'Bus',
        on_delete=models.CASCADE,
        related_name='verifications',
        verbose_name=_('bus'),
    )
    
    verified_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='bus_verifications',
        verbose_name=_('verified by'),
        null=True,
        blank=True,
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=APPLICATION_STATUSES,
        default=APPLICATION_STATUS_PENDING,
    )
    
    verification_date = models.DateTimeField(
        _('verification date'),
        null=True,
        blank=True,
    )
    
    rejection_reason = models.TextField(
        _('rejection reason'),
        blank=True,
    )
    
    notes = models.TextField(
        _('notes'),
        blank=True,
    )
    
    class Meta:
        verbose_name = _('bus verification')
        verbose_name_plural = _('bus verifications')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.bus.matricule} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Update bus verification status if approved or rejected
        if self.status == 'approved' and self.bus:
            self.bus.is_verified = True
            self.bus.verification_date = self.verification_date or timezone.now()
            self.bus.save(update_fields=['is_verified', 'verification_date'])
        elif self.status == 'rejected' and self.bus:
            self.bus.is_verified = False
            self.bus.save(update_fields=['is_verified'])
        
        super().save(*args, **kwargs)


class BusMaintenance(BaseModel):
    bus = models.ForeignKey(
        'Bus',
        on_delete=models.CASCADE,
        related_name='maintenance_records',
        verbose_name=_('bus'),
    )
    
    maintenance_type = models.CharField(
        _('maintenance type'),
        max_length=50,
        choices=(
            ('regular', _('Regular')),
            ('repair', _('Repair')),
            ('inspection', _('Inspection')),
            ('other', _('Other')),
        ),
    )
    
    date = models.DateTimeField(
        _('date'),
    )
    
    description = models.TextField(
        _('description'),
    )
    
    cost = models.DecimalField(
        _('cost'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    
    performed_by = models.CharField(
        _('performed by'),
        max_length=100,
        blank=True,
    )
    
    notes = models.TextField(
        _('notes'),
        blank=True,
    )
    
    class Meta:
        verbose_name = _('bus maintenance')
        verbose_name_plural = _('bus maintenances')
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.bus.matricule} - {self.get_maintenance_type_display()} - {self.date}"
    
    def save(self, *args, **kwargs):
        # Update bus last maintenance date
        if self.bus and self.date:
            update_fields = []
            
            # Update last maintenance if this is newer
            if not self.bus.last_maintenance or self.date > self.bus.last_maintenance:
                self.bus.last_maintenance = self.date
                update_fields.append('last_maintenance')
            
            # If fields were updated, save the bus
            if update_fields:
                self.bus.save(update_fields=update_fields)
        
        super().save(*args, **kwargs)