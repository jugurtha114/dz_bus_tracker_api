import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
#from phonenumber_field.modelfields import PhoneNumberField

from apps.core.constants import USER_TYPES, USER_TYPE_PASSENGER, LANGUAGES, LANGUAGE_FRENCH
from apps.core.base.models import TimeStampedModel, UUIDModel
from secrets import compare_digest


class UserManager(BaseUserManager):
    """
    Custom user manager for User model.
    """
    def create_user(self, email, **extra_fields):
        """
        Create and save a regular user with the given email and password.
        """
        if not email:
            raise ValueError(_('Email is required'))

        password = extra_fields.pop('password', None)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'admin')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True'))
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, UUIDModel):
    """
    Custom user model with email as the username field.
    """
    # Override username field to make it non-unique
    username = models.CharField(
        _('username'),
        max_length=150,
        blank=True,
        null=True,
    )
    
    # Use email as the unique identifier
    email = models.EmailField(
        _('email address'),
        unique=True,
    )
    
    # Phone number field
    phone_number = models.CharField(
        _('phone number'),
        blank=True,
        null=True,
        max_length=20,
    )
    
    # User type
    user_type = models.CharField(
        _('user type'),
        max_length=20,
        choices=USER_TYPES,
        default=USER_TYPE_PASSENGER,
    )
    
    # Language preference
    language = models.CharField(
        _('language'),
        max_length=2,
        choices=LANGUAGES,
        default=LANGUAGE_FRENCH,
    )
    
    # Email verification
    is_email_verified = models.BooleanField(
        _('email verified'),
        default=False,
    )
    
    # Phone verification
    is_phone_verified = models.BooleanField(
        _('phone verified'),
        default=False,
    )
    
    # Set email as the username field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    # Use custom manager
    objects = UserManager()
    
    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """
        Return the user's full name.
        """
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email
    
    def get_short_name(self):
        """
        Return the user's short name.
        """
        return self.first_name or self.email.split('@')[0]
    
    @property
    def is_admin(self):
        """
        Check if the user is an admin.
        """
        return self.user_type == 'admin'
    
    @property
    def is_driver(self):
        """
        Check if the user is a driver.
        """
        return self.user_type == 'driver'
    
    @property
    def is_passenger(self):
        """
        Check if the user is a passenger.
        """
        return self.user_type == 'passenger'


class UserProfile(TimeStampedModel, UUIDModel):
    """
    User profile model with additional user information.
    """
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_('user'),
    )
    
    profile_picture = models.ImageField(
        _('profile picture'),
        upload_to='profile_pictures/',
        blank=True,
        null=True,
    )
    
    fcm_token = models.CharField(
        _('FCM token'),
        max_length=255,
        blank=True,
        null=True,
    )
    
    notification_preferences = models.JSONField(
        _('notification preferences'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('user profile')
        verbose_name_plural = _('user profiles')
    
    def __str__(self):
        return f"Profile for {self.user.email}"
    
    def save(self, *args, **kwargs):
        """
        Override save method to initialize notification preferences.
        """
        if not self.notification_preferences:
            self.notification_preferences = {
                'push': True,
                'email': True,
                'sms': self.user.is_phone_verified,
                'app': True,
            }
        
        super().save(*args, **kwargs)


class VerificationToken(TimeStampedModel, UUIDModel):
    """
    Model for verification tokens for email and phone verification.
    """
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='verification_tokens',
        verbose_name=_('user'),
    )
    
    token = models.CharField(
        _('token'),
        max_length=64,
        unique=True,
    )
    
    token_type = models.CharField(
        _('token type'),
        max_length=20,
        choices=(
            ('email', _('Email')),
            ('phone', _('Phone')),
            ('password', _('Password Reset')),
        ),
    )
    
    expires_at = models.DateTimeField(
        _('expires at'),
    )
    
    is_used = models.BooleanField(
        _('used'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('verification token')
        verbose_name_plural = _('verification tokens')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.token_type.capitalize()} token for {self.user.email}"
    
    @property
    def is_expired(self):
        """
        Check if the token is expired.
        """
        from django.utils import timezone
        return timezone.now() > self.expires_at
