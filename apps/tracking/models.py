"""
Models for the tracking app.
"""
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.buses.models import Bus
from apps.core.constants import (
    BUS_TRACKING_STATUS_CHOICES,
    BUS_TRACKING_STATUS_IDLE,
)
from apps.core.models import BaseModel
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop


class BusLine(BaseModel):
    """
    Model for bus-line assignments.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("bus"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="buses",
        verbose_name=_("line"),
    )
    is_active = models.BooleanField(_("active"), default=True)
    tracking_status = models.CharField(
        _("tracking status"),
        max_length=20,
        choices=BUS_TRACKING_STATUS_CHOICES,
        default=BUS_TRACKING_STATUS_IDLE,
    )
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    start_time = models.DateTimeField(
        _("start time"),
        null=True,
        blank=True,
    )
    end_time = models.DateTimeField(
        _("end time"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("bus line")
        verbose_name_plural = _("bus lines")
        ordering = ["-created_at"]
        unique_together = [["bus", "line"]]

    def __str__(self):
        return f"{self.bus} on {self.line}"


class LocationUpdate(BaseModel):
    """
    Model for bus location updates.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="location_updates",
        verbose_name=_("bus"),
    )
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
    )
    altitude = models.DecimalField(
        _("altitude"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    speed = models.DecimalField(
        _("speed"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Speed in km/h"),
    )
    heading = models.DecimalField(
        _("heading"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Heading in degrees (0-360)"),
    )
    accuracy = models.DecimalField(
        _("accuracy"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Accuracy in meters"),
    )
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    nearest_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_updates",
        verbose_name=_("nearest stop"),
    )
    distance_to_stop = models.DecimalField(
        _("distance to stop"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance to nearest stop in meters"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_updates",
        verbose_name=_("line"),
    )

    class Meta:
        verbose_name = _("location update")
        verbose_name_plural = _("location updates")
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["bus", "-created_at"]),
            models.Index(fields=["line", "-created_at"]),
            models.Index(fields=["trip_id"]),
        ]

    def __str__(self):
        return f"{self.bus} at {self.created_at}"


class PassengerCount(BaseModel):
    """
    Model for passenger count updates.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="passenger_counts",
        verbose_name=_("bus"),
    )
    count = models.PositiveSmallIntegerField(_("count"))
    capacity = models.PositiveSmallIntegerField(
        _("capacity"),
        help_text=_("Total capacity of the bus"),
    )
    occupancy_rate = models.DecimalField(
        _("occupancy rate"),
        max_digits=5,
        decimal_places=2,
        help_text=_("Occupancy rate (0-1)"),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="passenger_counts",
        verbose_name=_("stop"),
        help_text=_("Stop where the count was recorded"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="passenger_counts",
        verbose_name=_("line"),
    )

    class Meta:
        verbose_name = _("passenger count")
        verbose_name_plural = _("passenger counts")
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["bus", "-created_at"]),
            models.Index(fields=["line", "-created_at"]),
            models.Index(fields=["trip_id"]),
        ]

    def __str__(self):
        return f"{self.bus}: {self.count} passengers at {self.created_at}"


class WaitingPassengers(BaseModel):
    """
    Model for waiting passengers at a stop.
    """
    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name="waiting_passengers",
        verbose_name=_("stop"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="waiting_passengers",
        verbose_name=_("line"),
        null=True,
        blank=True,
    )
    count = models.PositiveSmallIntegerField(_("count"))
    reported_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_waiting",
        verbose_name=_("reported by"),
    )

    class Meta:
        verbose_name = _("waiting passengers")
        verbose_name_plural = _("waiting passengers")
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return f"{self.stop}: {self.count} waiting at {self.created_at}"


class Trip(BaseModel):
    """
    Model for bus trips.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("bus"),
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("driver"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("line"),
    )
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(
        _("end time"),
        null=True,
        blank=True,
    )
    start_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_starts",
        verbose_name=_("start stop"),
    )
    end_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_ends",
        verbose_name=_("end stop"),
    )
    is_completed = models.BooleanField(_("completed"), default=False)
    distance = models.DecimalField(
        _("distance"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance traveled in km"),
    )
    average_speed = models.DecimalField(
        _("average speed"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Average speed in km/h"),
    )
    max_passengers = models.PositiveSmallIntegerField(
        _("max passengers"),
        default=0,
        help_text=_("Maximum number of passengers during the trip"),
    )
    total_stops = models.PositiveSmallIntegerField(
        _("total stops"),
        default=0,
        help_text=_("Total number of stops made"),
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("trip")
        verbose_name_plural = _("trips")
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["bus", "-start_time"]),
            models.Index(fields=["driver", "-start_time"]),
            models.Index(fields=["line", "-start_time"]),
        ]

    def __str__(self):
        return f"{self.bus} on {self.line} at {self.start_time}"


class Anomaly(BaseModel):
    """
    Model for tracking anomalies.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name=_("bus"),
    )
    trip = models.ForeignKey(
        Trip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomalies",
        verbose_name=_("trip"),
    )
    type = models.CharField(
        _("type"),
        max_length=50,
        choices=[
            ("speed", _("Speed anomaly")),
            ("route", _("Route deviation")),
            ("schedule", _("Schedule deviation")),
            ("passengers", _("Unusual passenger count")),
            ("gap", _("Service gap")),
            ("bunching", _("Bus bunching")),
            ("other", _("Other")),
        ],
    )
    description = models.TextField(_("description"))
    severity = models.CharField(
        _("severity"),
        max_length=20,
        choices=[
            ("low", _("Low")),
            ("medium", _("Medium")),
            ("high", _("High")),
        ],
        default="medium",
    )
    location_latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    location_longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    resolved = models.BooleanField(_("resolved"), default=False)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    resolution_notes = models.TextField(_("resolution notes"), blank=True)

    class Meta:
        verbose_name = _("anomaly")
        verbose_name_plural = _("anomalies")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} anomaly for {self.bus} at {self.created_at}"


class RouteSegment(BaseModel):
    """
    Store route segments between stops for visualization.
    """
    from_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='route_segments_from'
    )
    to_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='route_segments_to'
    )
    polyline = models.TextField(
        help_text=_('Encoded polyline for the route segment')
    )
    distance = models.FloatField(
        help_text=_('Distance in kilometers')
    )
    duration = models.IntegerField(
        help_text=_('Estimated duration in minutes')
    )
    
    class Meta:
        db_table = 'tracking_route_segments'
        unique_together = ['from_stop', 'to_stop']
        indexes = [
            models.Index(fields=['from_stop', 'to_stop']),
        ]
    
    def __str__(self):
        return f"{self.from_stop} -> {self.to_stop}"


class BusWaitingList(BaseModel):
    """
    Model for passengers waiting for specific buses.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="waiting_passengers",
        verbose_name=_("bus"),
    )
    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name="bus_waiting_lists",
        verbose_name=_("stop"),
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="waiting_lists",
        verbose_name=_("user"),
    )
    joined_at = models.DateTimeField(
        _("joined at"),
        auto_now_add=True
    )
    estimated_arrival = models.DateTimeField(
        _("estimated arrival"),
        null=True,
        blank=True,
        help_text=_("Bus ETA when user joined the waiting list")
    )
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        help_text=_("Whether the user is still waiting")
    )
    notified_on_arrival = models.BooleanField(
        _("notified on arrival"),
        default=False
    )
    left_at = models.DateTimeField(
        _("left at"),
        null=True,
        blank=True,
        help_text=_("When user left the waiting list")
    )

    class Meta:
        verbose_name = _("bus waiting list")
        verbose_name_plural = _("bus waiting lists")
        ordering = ["-joined_at"]
        unique_together = [["bus", "stop", "user"]]
        indexes = [
            models.Index(fields=["bus", "stop", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.email} waiting for {self.bus} at {self.stop}"


class ReputationScore(BaseModel):
    """
    Model for tracking user's reporting accuracy and reputation.
    """
    REPUTATION_LEVELS = [
        ('bronze', _('Bronze')),
        ('silver', _('Silver')),
        ('gold', _('Gold')),
        ('platinum', _('Platinum')),
    ]

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="reputation_score",
        verbose_name=_("user"),
    )
    total_reports = models.PositiveIntegerField(
        _("total reports"),
        default=0
    )
    correct_reports = models.PositiveIntegerField(
        _("correct reports"),
        default=0
    )
    reputation_level = models.CharField(
        _("reputation level"),
        max_length=20,
        choices=REPUTATION_LEVELS,
        default='bronze'
    )
    trust_multiplier = models.DecimalField(
        _("trust multiplier"),
        max_digits=3,
        decimal_places=2,
        default=1.00,
        help_text=_("Weight given to user's reports (0.50-2.00)")
    )
    last_updated = models.DateTimeField(
        _("last updated"),
        auto_now=True
    )

    class Meta:
        verbose_name = _("reputation score")
        verbose_name_plural = _("reputation scores")

    def __str__(self):
        return f"{self.user.email} - {self.reputation_level}"

    @property
    def accuracy_rate(self):
        """Calculate accuracy rate as percentage."""
        if self.total_reports == 0:
            return 0
        return (self.correct_reports / self.total_reports) * 100

    def update_reputation(self):
        """Update reputation level based on accuracy rate."""
        accuracy = self.accuracy_rate
        
        if accuracy >= 95:
            self.reputation_level = 'platinum'
            self.trust_multiplier = 2.00
        elif accuracy >= 85:
            self.reputation_level = 'gold'
            self.trust_multiplier = 1.50
        elif accuracy >= 70:
            self.reputation_level = 'silver'
            self.trust_multiplier = 1.00
        else:
            self.reputation_level = 'bronze'
            self.trust_multiplier = 0.50
        
        self.save()


class WaitingCountReport(BaseModel):
    """
    Model for crowdsourced waiting count reports.
    """
    CONFIDENCE_LEVELS = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
    ]

    VERIFICATION_STATUS = [
        ('pending', _('Pending')),
        ('correct', _('Correct')),
        ('incorrect', _('Incorrect')),
        ('partially_correct', _('Partially Correct')),
    ]

    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name="waiting_count_reports",
        verbose_name=_("stop"),
    )
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="waiting_count_reports",
        verbose_name=_("bus"),
        null=True,
        blank=True,
        help_text=_("Specific bus they're waiting for")
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="waiting_count_reports",
        verbose_name=_("line"),
        null=True,
        blank=True,
        help_text=_("Line they're waiting for")
    )
    reported_count = models.PositiveSmallIntegerField(
        _("reported count"),
        help_text=_("Number of people waiting as reported by user")
    )
    reporter = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="waiting_reports",
        verbose_name=_("reporter"),
    )
    confidence_level = models.CharField(
        _("confidence level"),
        max_length=10,
        choices=CONFIDENCE_LEVELS,
        default='medium'
    )
    confidence_score = models.DecimalField(
        _("confidence score"),
        max_digits=5,
        decimal_places=3,
        default=0.500,
        help_text=_("System-calculated accuracy score (0-1)")
    )
    is_verified = models.BooleanField(
        _("is verified"),
        default=False
    )
    verification_status = models.CharField(
        _("verification status"),
        max_length=20,
        choices=VERIFICATION_STATUS,
        default='pending'
    )
    verified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_reports",
        verbose_name=_("verified by"),
    )
    actual_count = models.PositiveSmallIntegerField(
        _("actual count"),
        null=True,
        blank=True,
        help_text=_("Actual count as verified by driver")
    )
    verified_at = models.DateTimeField(
        _("verified at"),
        null=True,
        blank=True
    )
    location_verified = models.BooleanField(
        _("location verified"),
        default=False,
        help_text=_("GPS confirms reporter is at stop")
    )
    reporter_latitude = models.DecimalField(
        _("reporter latitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )
    reporter_longitude = models.DecimalField(
        _("reporter longitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("waiting count report")
        verbose_name_plural = _("waiting count reports")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stop", "bus", "-created_at"]),
            models.Index(fields=["reporter", "-created_at"]),
            models.Index(fields=["verification_status"]),
        ]

    def __str__(self):
        return f"{self.reporter.email} reported {self.reported_count} waiting at {self.stop}"


class VirtualCurrency(BaseModel):
    """
    Model for user's virtual currency balance.
    """
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="virtual_currency",
        verbose_name=_("user"),
    )
    balance = models.IntegerField(
        _("balance"),
        default=0,
        help_text=_("Current virtual currency balance")
    )
    lifetime_earned = models.IntegerField(
        _("lifetime earned"),
        default=0
    )
    lifetime_spent = models.IntegerField(
        _("lifetime spent"),
        default=0
    )
    last_transaction = models.DateTimeField(
        _("last transaction"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("virtual currency")
        verbose_name_plural = _("virtual currencies")

    def __str__(self):
        return f"{self.user.email} - {self.balance} coins"

    def add_currency(self, amount, description="", transaction_type="earned"):
        """Add virtual currency to user's balance."""
        if amount > 0:
            self.balance += amount
            self.lifetime_earned += amount
        else:
            self.balance += amount  # amount is negative for spending/penalties
            self.lifetime_spent += abs(amount)
        
        self.last_transaction = timezone.now()
        self.save()

        # Create transaction record
        CurrencyTransaction.objects.create(
            user=self.user,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            balance_after=self.balance
        )


class CurrencyTransaction(BaseModel):
    """
    Model for tracking all virtual currency movements.
    """
    TRANSACTION_TYPES = [
        # Passenger transactions
        ('accurate_report', _('Accurate Report')),
        ('false_report', _('False Report')),
        ('waiting_bonus', _('Waiting Bonus')),
        ('consistency_bonus', _('Consistency Bonus')),
        ('early_adopter', _('Early Adopter Bonus')),
        ('driver_verification', _('Driver Verification Bonus')),
        ('reward_purchase', _('Reward Purchase')),
        ('penalty', _('Penalty')),
        ('admin_adjustment', _('Admin Adjustment')),
        
        # Driver transactions
        ('on_time_performance', _('On-Time Performance Bonus')),
        ('excellent_service', _('Excellent Service Rating')),
        ('safe_driving', _('Safe Driving Bonus')),
        ('fuel_efficiency', _('Fuel Efficiency Bonus')),
        ('passenger_satisfaction', _('High Passenger Satisfaction')),
        ('route_completion', _('Route Completion Bonus')),
        ('verification_accuracy', _('Report Verification Accuracy')),
        ('weekly_achievement', _('Weekly Achievement')),
        ('monthly_achievement', _('Monthly Achievement')),
        ('premium_purchase', _('Premium Feature Purchase')),
        ('achievement_unlock', _('Achievement Unlocked')),
        ('streak_bonus', _('Performance Streak Bonus')),
    ]

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="currency_transactions",
        verbose_name=_("user"),
    )
    amount = models.IntegerField(
        _("amount"),
        help_text=_("Positive for earning, negative for spending/penalty")
    )
    transaction_type = models.CharField(
        _("transaction type"),
        max_length=30,
        choices=TRANSACTION_TYPES
    )
    description = models.CharField(
        _("description"),
        max_length=255
    )
    balance_after = models.IntegerField(
        _("balance after"),
        help_text=_("User's balance after this transaction")
    )
    related_report = models.ForeignKey(
        WaitingCountReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="currency_transactions",
        verbose_name=_("related report"),
    )
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        blank=True,
        help_text=_("Additional transaction data")
    )

    class Meta:
        verbose_name = _("currency transaction")
        verbose_name_plural = _("currency transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["transaction_type"]),
        ]

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.user.email}: {sign}{self.amount} coins - {self.description}"


class DriverPerformanceScore(BaseModel):
    """
    Model for tracking driver's performance metrics and achievements.
    """
    PERFORMANCE_LEVELS = [
        ('rookie', _('Rookie')),
        ('experienced', _('Experienced')), 
        ('expert', _('Expert')),
        ('master', _('Master')),
    ]

    driver = models.OneToOneField(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name="performance_score",
        verbose_name=_("driver"),
    )
    total_trips = models.PositiveIntegerField(
        _("total trips"),
        default=0
    )
    on_time_trips = models.PositiveIntegerField(
        _("on-time trips"),
        default=0
    )
    performance_level = models.CharField(
        _("performance level"),
        max_length=20,
        choices=PERFORMANCE_LEVELS,
        default='rookie'
    )
    safety_score = models.DecimalField(
        _("safety score"),
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    passenger_rating = models.DecimalField(
        _("passenger rating"),
        max_digits=3,
        decimal_places=2,
        default=5.00,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    fuel_efficiency_score = models.DecimalField(
        _("fuel efficiency score"),
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(200)]
    )
    report_verification_accuracy = models.DecimalField(
        _("report verification accuracy"),
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    current_streak = models.PositiveIntegerField(
        _("current performance streak"),
        default=0,
        help_text=_("Days of excellent performance")
    )
    best_streak = models.PositiveIntegerField(
        _("best performance streak"),
        default=0
    )
    last_updated = models.DateTimeField(
        _("last updated"),
        auto_now=True
    )

    class Meta:
        verbose_name = _("driver performance score")
        verbose_name_plural = _("driver performance scores")

    def __str__(self):
        return f"{self.driver.user.email} - {self.performance_level}"

    @property
    def on_time_percentage(self):
        """Calculate on-time performance percentage."""
        if self.total_trips == 0:
            return 100.0
        return (self.on_time_trips / self.total_trips) * 100

    def update_performance_level(self):
        """Update performance level based on metrics."""
        on_time_pct = self.on_time_percentage
        
        if (on_time_pct >= 95 and self.safety_score >= 95 and 
            self.passenger_rating >= 4.5 and self.total_trips >= 100):
            self.performance_level = 'master'
        elif (on_time_pct >= 90 and self.safety_score >= 90 and 
              self.passenger_rating >= 4.0 and self.total_trips >= 50):
            self.performance_level = 'expert'
        elif (on_time_pct >= 80 and self.safety_score >= 85 and 
              self.passenger_rating >= 3.5 and self.total_trips >= 20):
            self.performance_level = 'experienced'
        else:
            self.performance_level = 'rookie'
        
        self.save()


class PremiumFeature(BaseModel):
    """
    Model for premium features that can be purchased with virtual currency.
    """
    # NOTE: Only passenger/general feature types are listed here.
    # Driver-targeted feature types (fuel_optimization, earnings_tracker,
    # schedule_optimizer, maintenance_alerts, competition_stats) were removed
    # in Phase 3 cleanup to keep premium features passenger-focused.
    # Any existing DB rows with the removed feature_type values remain valid;
    # they simply will not appear as purchasable options in the UI.
    FEATURE_TYPES = [
        ('route_analytics', _('Advanced Route Analytics')),
        ('performance_insights', _('Detailed Performance Insights')),
        ('passenger_feedback', _('Real-time Passenger Feedback')),
        ('priority_support', _('Priority Customer Support')),
        ('custom_dashboard', _('Customizable Dashboard')),
    ]

    TARGET_USERS = [
        ('passengers', _('Passengers')),
        ('drivers', _('Drivers')),
        ('all', _('All Users')),
    ]

    name = models.CharField(
        _("feature name"),
        max_length=100
    )
    feature_type = models.CharField(
        _("feature type"),
        max_length=30,
        choices=FEATURE_TYPES
    )
    description = models.TextField(
        _("description")
    )
    cost_coins = models.PositiveIntegerField(
        _("cost in coins"),
        help_text=_("Cost to unlock this feature")
    )
    duration_days = models.PositiveIntegerField(
        _("duration in days"),
        default=30,
        help_text=_("How long the feature stays active")
    )
    target_users = models.CharField(
        _("target users"),
        max_length=20,
        choices=TARGET_USERS,
        default='all'
    )
    is_active = models.BooleanField(
        _("is active"),
        default=True
    )
    required_level = models.CharField(
        _("required performance level"),
        max_length=20,
        choices=DriverPerformanceScore.PERFORMANCE_LEVELS,
        null=True,
        blank=True,
        help_text=_("Minimum performance level required (drivers only)")
    )

    class Meta:
        verbose_name = _("premium feature")
        verbose_name_plural = _("premium features")

    def __str__(self):
        return f"{self.name} - {self.cost_coins} coins"


class UserPremiumFeature(BaseModel):
    """
    Model for tracking user's purchased premium features.
    """
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name="premium_features",
        verbose_name=_("user"),
    )
    feature = models.ForeignKey(
        PremiumFeature,
        on_delete=models.CASCADE,
        related_name="user_purchases",
        verbose_name=_("feature"),
    )
    purchased_at = models.DateTimeField(
        _("purchased at"),
        auto_now_add=True
    )
    expires_at = models.DateTimeField(
        _("expires at")
    )
    is_active = models.BooleanField(
        _("is active"),
        default=True
    )
    coins_spent = models.PositiveIntegerField(
        _("coins spent")
    )

    class Meta:
        verbose_name = _("user premium feature")
        verbose_name_plural = _("user premium features")
        unique_together = [["user", "feature"]]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["feature", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.feature.name}"

    @property
    def is_expired(self):
        """Check if the feature has expired."""
        return timezone.now() > self.expires_at

    def deactivate_if_expired(self):
        """Deactivate feature if expired."""
        if self.is_expired and self.is_active:
            self.is_active = False
            self.save()




__all__ = [
    'LocationUpdate',
    'Trip',
    'PassengerCount',
    'WaitingPassengers',
    'BusLine',
    'Anomaly',
    'RouteSegment',
    'BusWaitingList',
    'WaitingCountReport',
    'ReputationScore',
    'VirtualCurrency',
    'CurrencyTransaction',
    'DriverPerformanceScore',
    'PremiumFeature',
    'UserPremiumFeature',
]