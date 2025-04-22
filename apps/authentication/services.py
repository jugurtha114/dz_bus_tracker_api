import uuid
import secrets
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserProfile, VerificationToken


def create_user(user_data):
    """
    Create a new user and user profile.
    
    Args:
        user_data: Dictionary containing user data
        
    Returns:
        Newly created user
    """
    # Extract password
    password = user_data.pop('password', None)
    
    # Create user
    user = User.objects.create_user(**user_data)
    
    # Set password
    if password:
        user.set_password(password)
        user.save(update_fields=['password'])
    
    # Create user profile
    UserProfile.objects.create(user=user)
    
    # Send verification email
    send_verification_email(user)
    
    return user


def update_user(user, user_data):
    """
    Update an existing user.
    
    Args:
        user: User to update
        user_data: Dictionary containing user data
        
    Returns:
        Updated user
    """
    # Phone number verification reset if changed
    if 'phone_number' in user_data and user_data['phone_number'] != user.phone_number:
        user.is_phone_verified = False
    
    # Update user
    for attr, value in user_data.items():
        setattr(user, attr, value)
    
    user.save()
    
    return user


def update_user_profile(user, profile_data):
    """
    Update an existing user profile.
    
    Args:
        user: User whose profile to update
        profile_data: Dictionary containing profile data
        
    Returns:
        Updated user profile
    """
    # Get profile
    profile = user.profile
    
    # Update profile
    for attr, value in profile_data.items():
        setattr(profile, attr, value)
    
    profile.save()
    
    return profile


def create_verification_token(user, token_type):
    """
    Create a verification token for a user.
    
    Args:
        user: User to create token for
        token_type: Type of token to create
        
    Returns:
        Newly created verification token
    """
    # Generate token
    token = secrets.token_urlsafe(32)
    
    # Set expiration time (24 hours)
    expires_at = timezone.now() + timedelta(hours=24)
    
    # Create verification token
    verification_token = VerificationToken.objects.create(
        user=user,
        token=token,
        token_type=token_type,
        expires_at=expires_at,
    )
    
    return verification_token


def send_verification_email(user):
    """
    Send a verification email to a user.
    
    Args:
        user: User to send email to
        
    Returns:
        Boolean indicating success
    """
    # Create verification token
    verification_token = create_verification_token(user, 'email')
    
    # Build verification URL
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token.token}"
    
    # Prepare email
    subject = "Verify your email address"
    html_message = render_to_string(
        'emails/verify_email.html',
        {
            'user': user,
            'verify_url': verify_url,
        }
    )
    
    # Send email
    sent = send_mail(
        subject=subject,
        message="",
        html_message=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    
    return sent > 0


def send_verification_sms(user):
    """
    Send a verification SMS to a user.
    
    Args:
        user: User to send SMS to
        
    Returns:
        Boolean indicating success
    """
    # Create verification token
    verification_token = create_verification_token(user, 'phone')
    
    # Generate verification code (6 digits)
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # Save code in token
    verification_token.token = code
    verification_token.save(update_fields=['token'])
    
    # Prepare message
    message = f"Your DZ Bus Tracker verification code is: {code}"
    
    # Send SMS
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        message = client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=str(user.phone_number),
        )
        
        return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


def verify_email(token):
    """
    Verify a user's email address using a verification token.
    
    Args:
        token: Verification token
        
    Returns:
        User whose email was verified
    """
    # Find token in database
    try:
        verification_token = VerificationToken.objects.get(
            token=token,
            token_type='email',
            is_used=False,
        )
    except VerificationToken.DoesNotExist:
        return None
    
    # Check if token is expired
    if verification_token.is_expired:
        return None
    
    # Get user
    user = verification_token.user
    
    # Verify email
    user.is_email_verified = True
    user.save(update_fields=['is_email_verified'])
    
    # Mark token as used
    verification_token.is_used = True
    verification_token.save(update_fields=['is_used'])
    
    return user


def verify_phone(token):
    """
    Verify a user's phone number using a verification token.
    
    Args:
        token: Verification token
        
    Returns:
        User whose phone was verified
    """
    # Find token in database
    try:
        verification_token = VerificationToken.objects.get(
            token=token,
            token_type='phone',
            is_used=False,
        )
    except VerificationToken.DoesNotExist:
        return None
    
    # Check if token is expired
    if verification_token.is_expired:
        return None
    
    # Get user
    user = verification_token.user
    
    # Verify phone
    user.is_phone_verified = True
    user.save(update_fields=['is_phone_verified'])
    
    # Mark token as used
    verification_token.is_used = True
    verification_token.save(update_fields=['is_used'])
    
    return user


def generate_tokens(user):
    """
    Generate JWT tokens for a user.
    
    Args:
        user: User to generate tokens for
        
    Returns:
        Dictionary containing tokens
    """
    refresh = RefreshToken.for_user(user)
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def change_password(user, current_password, new_password):
    """
    Change a user's password.
    
    Args:
        user: User to change password for
        current_password: Current password
        new_password: New password
        
    Returns:
        Boolean indicating success
    """
    # Check current password
    if not user.check_password(current_password):
        return False
    
    # Set new password
    user.set_password(new_password)
    user.save(update_fields=['password'])
    
    return True


def reset_password_request(email):
    """
    Request a password reset for a user.
    
    Args:
        email: Email of user to reset password for
        
    Returns:
        Boolean indicating success
    """
    # Find user
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False
    
    # Create verification token
    verification_token = create_verification_token(user, 'password')
    
    # Build reset URL
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={verification_token.token}"
    
    # Prepare email
    subject = "Reset your password"
    html_message = render_to_string(
        'emails/reset_password.html',
        {
            'user': user,
            'reset_url': reset_url,
        }
    )
    
    # Send email
    sent = send_mail(
        subject=subject,
        message="",
        html_message=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    
    return sent > 0


def reset_password(token, new_password):
    """
    Reset a user's password using a verification token.
    
    Args:
        token: Verification token
        new_password: New password
        
    Returns:
        User whose password was reset
    """
    # Find token in database
    try:
        verification_token = VerificationToken.objects.get(
            token=token,
            token_type='password',
            is_used=False,
        )
    except VerificationToken.DoesNotExist:
        return None
    
    # Check if token is expired
    if verification_token.is_expired:
        return None
    
    # Get user
    user = verification_token.user
    
    # Set new password
    user.set_password(new_password)
    user.save(update_fields=['password'])
    
    # Mark token as used
    verification_token.is_used = True
    verification_token.save(update_fields=['is_used'])
    
    return user


def update_fcm_token(user, fcm_token):
    """
    Update a user's FCM token.
    
    Args:
        user: User to update
        fcm_token: New FCM token
        
    Returns:
        Updated user profile
    """
    # Get profile
    profile = user.profile
    
    # Update FCM token
    profile.fcm_token = fcm_token
    profile.save(update_fields=['fcm_token'])
    
    return profile


def update_notification_preferences(user, preferences):
    """
    Update a user's notification preferences.
    
    Args:
        user: User to update
        preferences: New notification preferences
        
    Returns:
        Updated user profile
    """
    # Get profile
    profile = user.profile
    
    # Update notification preferences
    profile.notification_preferences.update(preferences)
    profile.save(update_fields=['notification_preferences'])
    
    return profile