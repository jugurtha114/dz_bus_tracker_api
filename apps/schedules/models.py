from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import ArrayField

from apps.core.base.models import BaseModel
from apps.core.constants import DAY_MONDAY, DAY_TUESDAY, DAY_WEDNESDAY, DAY_THURSDAY, DAY_FRIDAY, DAY_SATURDAY, DAY_SUNDAY


class Schedule(BaseModel):
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name=_('line'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name=_('bus'),
    )
    
    driver = models.ForeignKey(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name=_('driver'),
    )
    
    start_time = models.TimeField(
        _('start time'),
    )
    
    end_time = models.TimeField(
        _('end time'),
    )
    
    days_of_week = ArrayField(
        models.PositiveSmallIntegerField(
            choices=(
                (DAY_MONDAY, _('Monday')),
                (DAY_TUESDAY, _('Tuesday')),
                (DAY_WEDNESDAY, _('Wednesday')),
                (DAY_THURSDAY, _('Thursday')),
                (DAY_FRIDAY, _('Friday')),
                (DAY_SATURDAY, _('Saturday')),
                (DAY_SUNDAY, _('Sunday')),
            ),
        ),
        verbose_name=_('days of week'),
    )
    
    frequency = models.PositiveIntegerField(
        _('frequency (minutes)'),
        default=0,
        help_text=_('How often the bus runs (0 for one-time)'),
    )
    
    is_peak_hour = models.BooleanField(
        _('peak hour'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('schedule')
        verbose_name_plural = _('schedules')
        ordering = ['line', 'start_time']
        indexes = [
            models.Index(fields=['line']),
            models.Index(fields=['bus']),
            models.Index(fields=['driver']),
            models.Index(fields=['start_time']),
        ]
    
    def __str__(self):
        days = ", ".join(str(self.get_days_of_week_display(day)) for day in self.days_of_week)
        return f"{self.line.name} - {self.bus.matricule} - {days} ({self.start_time} - {self.end_time})"
    
    def get_days_of_week_display(self, day):
        return dict(self._meta.get_field('days_of_week').base_field.choices)[day]


class ScheduleException(BaseModel):
    schedule = models.ForeignKey(
        'Schedule',
        on_delete=models.CASCADE,
        related_name='exceptions',
        verbose_name=_('schedule'),
    )
    
    date = models.DateField(
        _('date'),
    )
    
    is_cancelled = models.BooleanField(
        _('cancelled'),
        default=True,
    )
    
    reason = models.CharField(
        _('reason'),
        max_length=255,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('schedule exception')
        verbose_name_plural = _('schedule exceptions')
        ordering = ['date']
        unique_together = [['schedule', 'date']]
    
    def __str__(self):
        status = 'Cancelled' if self.is_cancelled else 'Modified'
        return f"{status} schedule for {self.schedule} on {self.date}"


class ScheduledTrip(BaseModel):
    schedule = models.ForeignKey(
        'Schedule',
        on_delete=models.CASCADE,
        related_name='trips',
        verbose_name=_('schedule'),
    )
    
    date = models.DateField(
        _('date'),
    )
    
    start_time = models.DateTimeField(
        _('start time'),
    )
    
    end_time = models.DateTimeField(
        _('end time'),
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=(
            ('scheduled', _('Scheduled')),
            ('in_progress', _('In Progress')),
            ('completed', _('Completed')),
            ('cancelled', _('Cancelled')),
            ('delayed', _('Delayed')),
        ),
        default='scheduled',
    )
    
    tracking_session = models.OneToOneField(
        'tracking.TrackingSession',
        on_delete=models.SET_NULL,
        related_name='scheduled_trip',
        verbose_name=_('tracking session'),
        null=True,
        blank=True,
    )
    
    actual_start_time = models.DateTimeField(
        _('actual start time'),
        null=True,
        blank=True,
    )
    
    actual_end_time = models.DateTimeField(
        _('actual end time'),
        null=True,
        blank=True,
    )
    
    delay_minutes = models.PositiveIntegerField(
        _('delay (minutes)'),
        default=0,
    )
    
    notes = models.TextField(
        _('notes'),
        blank=True,
    )
    
    class Meta:
        verbose_name = _('scheduled trip')
        verbose_name_plural = _('scheduled trips')
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['schedule']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['start_time']),
        ]
    
    def __str__(self):
        return f"{self.schedule} on {self.date} - {self.get_status_display()}"


class MaintenanceSchedule(BaseModel):
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='maintenance_schedules',
        verbose_name=_('bus'),
    )
    
    start_date = models.DateField(
        _('start date'),
    )
    
    end_date = models.DateField(
        _('end date'),
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
    
    description = models.TextField(
        _('description'),
        blank=True,
    )
    
    is_completed = models.BooleanField(
        _('completed'),
        default=False,
    )
    
    completed_at = models.DateTimeField(
        _('completed at'),
        null=True,
        blank=True,
    )
    
    notes = models.TextField(
        _('notes'),
        blank=True,
    )
    
    class Meta:
        verbose_name = _('maintenance schedule')
        verbose_name_plural = _('maintenance schedules')
        ordering = ['start_date']
    
    def __str__(self):
        return f"{self.bus.matricule} - {self.get_maintenance_type_display()} ({self.start_date} - {self.end_date})"
