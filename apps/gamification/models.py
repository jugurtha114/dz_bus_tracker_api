"""
Models for the gamification app.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel
from apps.buses.models import Bus
from apps.lines.models import Line, Stop
from apps.tracking.models import Trip

User = get_user_model()


class UserProfile(BaseModel):
    """
    Extended user profile for gamification data.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='gamification_profile',
        verbose_name=_("user")
    )
    
    # Points and levels
    total_points = models.IntegerField(_("total points"), default=0)
    current_level = models.IntegerField(_("current level"), default=1)
    experience_points = models.IntegerField(_("experience points"), default=0)
    
    # Statistics
    total_trips = models.IntegerField(_("total trips"), default=0)
    total_distance = models.DecimalField(
        _("total distance"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    carbon_saved = models.DecimalField(
        _("carbon saved (kg)"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    # Streaks
    current_streak = models.IntegerField(_("current streak"), default=0)
    longest_streak = models.IntegerField(_("longest streak"), default=0)
    last_trip_date = models.DateField(_("last trip date"), null=True, blank=True)
    
    # Preferences
    receive_achievement_notifications = models.BooleanField(
        _("receive achievement notifications"),
        default=True
    )
    display_on_leaderboard = models.BooleanField(
        _("display on leaderboard"),
        default=True
    )
    
    class Meta:
        verbose_name = _("user profile")
        verbose_name_plural = _("user profiles")
        
    def __str__(self):
        return f"{self.user.email} - Level {self.current_level}"
    
    def add_points(self, points):
        """Add points and update level if needed."""
        self.total_points += points
        self.experience_points += points
        
        # Check for level up (100 points per level)
        while self.experience_points >= self.current_level * 100:
            self.experience_points -= self.current_level * 100
            self.current_level += 1
            
        self.save()
        return self.current_level


class Achievement(BaseModel):
    """
    Achievement definitions.
    """
    name = models.CharField(_("name"), max_length=100, unique=True)
    description = models.TextField(_("description"))
    icon = models.CharField(
        _("icon"),
        max_length=50,
        help_text=_("Icon identifier or emoji")
    )
    
    # Achievement requirements
    achievement_type = models.CharField(
        _("type"),
        max_length=30,
        choices=[
            ('trips', _('Number of Trips')),
            ('distance', _('Distance Traveled')),
            ('streak', _('Day Streak')),
            ('eco', _('Environmental Impact')),
            ('social', _('Social Engagement')),
            ('special', _('Special Achievement')),
            ('level', _('Level Based')),
        ]
    )
    
    # Thresholds
    threshold_value = models.IntegerField(
        _("threshold value"),
        default=0,
        help_text=_("Value needed to unlock")
    )
    
    # Rewards
    points_reward = models.IntegerField(_("points reward"), default=50)
    
    # Rarity
    rarity = models.CharField(
        _("rarity"),
        max_length=20,
        choices=[
            ('common', _('Common')),
            ('uncommon', _('Uncommon')),
            ('rare', _('Rare')),
            ('epic', _('Epic')),
            ('legendary', _('Legendary')),
        ],
        default='common'
    )
    
    # Display
    is_active = models.BooleanField(_("is active"), default=True)
    order = models.IntegerField(_("display order"), default=0)
    
    class Meta:
        verbose_name = _("achievement")
        verbose_name_plural = _("achievements")
        ordering = ['order', 'name']
        
    def __str__(self):
        return self.name


class UserAchievement(BaseModel):
    """
    User's earned achievements.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='achievements',
        verbose_name=_("user")
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='user_achievements',
        verbose_name=_("achievement")
    )
    unlocked_at = models.DateTimeField(
        _("unlocked at"),
        auto_now_add=True
    )
    progress = models.IntegerField(
        _("progress"),
        default=0,
        help_text=_("Progress towards achievement")
    )
    is_notified = models.BooleanField(
        _("user notified"),
        default=False
    )
    
    class Meta:
        verbose_name = _("user achievement")
        verbose_name_plural = _("user achievements")
        unique_together = ['user', 'achievement']
        ordering = ['-unlocked_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.achievement.name}"


class PointTransaction(BaseModel):
    """
    Log of all point transactions.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='point_transactions',
        verbose_name=_("user")
    )
    
    transaction_type = models.CharField(
        _("transaction type"),
        max_length=30,
        choices=[
            ('trip_complete', _('Trip Completed')),
            ('achievement', _('Achievement Unlocked')),
            ('daily_bonus', _('Daily Bonus')),
            ('streak_bonus', _('Streak Bonus')),
            ('referral', _('Referral Bonus')),
            ('special_event', _('Special Event')),
            ('penalty', _('Penalty')),
        ]
    )
    
    points = models.IntegerField(_("points"))
    description = models.CharField(_("description"), max_length=255)
    
    # Related objects
    trip = models.ForeignKey(
        Trip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='point_transactions'
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='point_transactions'
    )
    
    # Metadata
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        blank=True
    )
    
    class Meta:
        verbose_name = _("point transaction")
        verbose_name_plural = _("point transactions")
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.points} points - {self.transaction_type}"


class Leaderboard(BaseModel):
    """
    Leaderboard entries for different time periods.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='leaderboard_entries',
        verbose_name=_("user")
    )
    
    period_type = models.CharField(
        _("period type"),
        max_length=20,
        choices=[
            ('daily', _('Daily')),
            ('weekly', _('Weekly')),
            ('monthly', _('Monthly')),
            ('all_time', _('All Time')),
        ]
    )
    
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"), null=True, blank=True)
    
    # Scores
    points = models.IntegerField(_("points"), default=0)
    trips = models.IntegerField(_("trips"), default=0)
    distance = models.DecimalField(
        _("distance"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    # Ranking
    rank = models.IntegerField(_("rank"), default=0)
    previous_rank = models.IntegerField(
        _("previous rank"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("leaderboard entry")
        verbose_name_plural = _("leaderboard entries")
        unique_together = ['user', 'period_type', 'period_start']
        ordering = ['period_type', '-points', 'rank']
        indexes = [
            models.Index(fields=['period_type', '-points']),
            models.Index(fields=['user', 'period_type']),
        ]
        
    def __str__(self):
        return f"{self.user.email} - {self.period_type} - Rank {self.rank}"


class Challenge(BaseModel):
    """
    Time-limited challenges for users.
    """
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"))
    
    challenge_type = models.CharField(
        _("challenge type"),
        max_length=30,
        choices=[
            ('individual', _('Individual Challenge')),
            ('community', _('Community Challenge')),
            ('route', _('Route Challenge')),
            ('eco', _('Eco Challenge')),
        ]
    )
    
    # Duration
    start_date = models.DateTimeField(_("start date"))
    end_date = models.DateTimeField(_("end date"))
    
    # Requirements
    target_value = models.IntegerField(
        _("target value"),
        help_text=_("Target to achieve")
    )
    current_value = models.IntegerField(
        _("current value"),
        default=0
    )
    
    # Rewards
    points_reward = models.IntegerField(_("points reward"))
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='challenges'
    )
    
    # Specific targets
    target_line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    target_stops = models.ManyToManyField(
        Stop,
        blank=True,
        related_name='challenges'
    )
    
    # Status
    is_active = models.BooleanField(_("is active"), default=True)
    is_completed = models.BooleanField(_("is completed"), default=False)
    
    class Meta:
        verbose_name = _("challenge")
        verbose_name_plural = _("challenges")
        ordering = ['-start_date']
        
    def __str__(self):
        return self.name
    
    @property
    def progress_percentage(self):
        """Calculate progress percentage."""
        if self.target_value == 0:
            return 0
        return min(100, int((self.current_value / self.target_value) * 100))


class UserChallenge(BaseModel):
    """
    User participation in challenges.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='challenges',
        verbose_name=_("user")
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name='participants',
        verbose_name=_("challenge")
    )
    
    # Progress
    progress = models.IntegerField(_("progress"), default=0)
    is_completed = models.BooleanField(_("is completed"), default=False)
    completed_at = models.DateTimeField(
        _("completed at"),
        null=True,
        blank=True
    )
    
    # Rewards
    points_earned = models.IntegerField(_("points earned"), default=0)
    is_rewarded = models.BooleanField(_("is rewarded"), default=False)
    
    class Meta:
        verbose_name = _("user challenge")
        verbose_name_plural = _("user challenges")
        unique_together = ['user', 'challenge']
        
    def __str__(self):
        return f"{self.user.email} - {self.challenge.name}"


class Reward(BaseModel):
    """
    Redeemable rewards using points.
    """
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"))
    
    reward_type = models.CharField(
        _("reward type"),
        max_length=30,
        choices=[
            ('discount', _('Discount Code')),
            ('free_ride', _('Free Ride')),
            ('merchandise', _('Merchandise')),
            ('donation', _('Charity Donation')),
            ('special', _('Special Reward')),
        ]
    )
    
    # Cost
    points_cost = models.IntegerField(_("points cost"))
    
    # Availability
    quantity_available = models.IntegerField(
        _("quantity available"),
        default=-1,
        help_text=_("-1 for unlimited")
    )
    quantity_redeemed = models.IntegerField(
        _("quantity redeemed"),
        default=0
    )
    
    # Validity
    valid_from = models.DateTimeField(_("valid from"))
    valid_until = models.DateTimeField(_("valid until"))
    
    # Display
    image = models.ImageField(
        _("image"),
        upload_to='rewards/',
        null=True,
        blank=True
    )
    is_active = models.BooleanField(_("is active"), default=True)
    
    # Partner info
    partner_name = models.CharField(
        _("partner name"),
        max_length=100,
        blank=True
    )
    
    class Meta:
        verbose_name = _("reward")
        verbose_name_plural = _("rewards")
        ordering = ['points_cost', 'name']
        
    def __str__(self):
        return f"{self.name} - {self.points_cost} points"
    
    @property
    def is_available(self):
        """Check if reward is available."""
        from django.utils import timezone
        now = timezone.now()
        
        if not self.is_active:
            return False
            
        if now < self.valid_from or now > self.valid_until:
            return False
            
        if self.quantity_available != -1:
            return self.quantity_redeemed < self.quantity_available
            
        return True


class UserReward(BaseModel):
    """
    User's redeemed rewards.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rewards',
        verbose_name=_("user")
    )
    reward = models.ForeignKey(
        Reward,
        on_delete=models.CASCADE,
        related_name='redemptions',
        verbose_name=_("reward")
    )
    
    # Redemption details
    points_spent = models.IntegerField(_("points spent"))
    redemption_code = models.CharField(
        _("redemption code"),
        max_length=50,
        unique=True
    )
    
    # Status
    is_used = models.BooleanField(_("is used"), default=False)
    used_at = models.DateTimeField(
        _("used at"),
        null=True,
        blank=True
    )
    
    # Validity
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("user reward")
        verbose_name_plural = _("user rewards")
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.reward.name}"
