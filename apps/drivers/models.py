from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel
from apps.core.constants import APPLICATION_STATUSES, APPLICATION_STATUS_PENDING


class Driver(BaseModel):
    user = models.OneToOneField(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='driver_profile',
        verbose_name=_('user'),
    )
    
    id_number = models.CharField(
        _('ID number'),
        max_length=50,
        unique=True,
    )
    
    id_photo = models.ImageField(
        _('ID photo'),
        upload_to='driver_ids/',
    )
    
    license_number = models.CharField(
        _('license number'),
        max_length=50,
        unique=True,
    )
    
    license_photo = models.ImageField(
        _('license photo'),
        upload_to='driver_licenses/',
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
    
    experience_years = models.PositiveIntegerField(
        _('experience years'),
        default=0,
    )
    
    date_of_birth = models.DateField(
        _('date of birth'),
        null=True,
        blank=True,
    )
    
    address = models.TextField(
        _('address'),
        blank=True,
    )
    
    emergency_contact = models.CharField(
        _('emergency contact'),
        max_length=100,
        blank=True,
    )
    
    notes = models.TextField(
        _('notes'),
        blank=True,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('driver')
        verbose_name_plural = _('drivers')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['id_number']),
            models.Index(fields=['license_number']),
            models.Index(fields=['is_verified']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.id_number})"
    
    @property
    def full_name(self):
        return self.user.get_full_name()
    
    @property
    def email(self):
        return self.user.email
    
    @property
    def phone_number(self):
        return self.user.phone_number
    
    @property
    def has_active_buses(self):
        return self.buses.filter(is_active=True).exists()
    
    @property
    def has_verified_buses(self):
        return self.buses.filter(is_verified=True, is_active=True).exists()
    
    @property
    def has_active_tracking(self):
        return self.tracking_sessions.filter(status='active', is_active=True).exists()
    
    @property
    def active_tracking_session(self):
        return self.tracking_sessions.filter(status='active', is_active=True).first()


class DriverApplication(BaseModel):
    driver = models.ForeignKey(
        'Driver',
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('driver'),
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=APPLICATION_STATUSES,
        default=APPLICATION_STATUS_PENDING,
    )
    
    reviewed_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        related_name='reviewed_driver_applications',
        verbose_name=_('reviewed by'),
        null=True,
        blank=True,
    )
    
    reviewed_at = models.DateTimeField(
        _('reviewed at'),
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
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('driver application')
        verbose_name_plural = _('driver applications')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Application for {self.driver} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Update driver verification status if application is approved or rejected
        if self.status == 'approved' and self.driver:
            self.driver.is_verified = True
            self.driver.verification_date = timezone.now()
            self.driver.save(update_fields=['is_verified', 'verification_date'])
            
            # Update user type to driver if not already
            if self.driver.user.user_type != 'driver':
                self.driver.user.user_type = 'driver'
                self.driver.user.save(update_fields=['user_type'])
        
        elif self.status == 'rejected' and self.driver:
            self.driver.is_verified = False
            self.driver.save(update_fields=['is_verified'])
        
        super().save(*args, **kwargs)


class DriverRating(BaseModel):
    driver = models.ForeignKey(
        'Driver',
        on_delete=models.CASCADE,
        related_name='ratings',
        verbose_name=_('driver'),
    )
    
    passenger = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='driver_ratings',
        verbose_name=_('passenger'),
    )
    
    rating = models.PositiveSmallIntegerField(
        _('rating'),
        choices=(
            (1, '1 - Poor'),
            (2, '2 - Below Average'),
            (3, '3 - Average'),
            (4, '4 - Good'),
            (5, '5 - Excellent'),
        ),
    )
    
    comment = models.TextField(
        _('comment'),
        blank=True,
    )
    
    trip = models.ForeignKey(
        'tracking.TrackingSession',
        on_delete=models.SET_NULL,
        related_name='driver_ratings',
        verbose_name=_('trip'),
        null=True,
        blank=True,
    )
    
    is_anonymous = models.BooleanField(
        _('anonymous'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('driver rating')
        verbose_name_plural = _('driver ratings')
        ordering = ['-created_at']
        # Ensure a user can only rate a driver once per trip
        unique_together = [['driver', 'passenger', 'trip']]
    
    def __str__(self):
        return f"Rating for {self.driver} by {self.passenger.get_full_name() if not self.is_anonymous else 'Anonymous'}"
