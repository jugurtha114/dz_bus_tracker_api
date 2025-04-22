from django.db.models import Prefetch, Q
from utils.cache import cached_result
from .models import User, UserProfile


@cached_result('user', timeout=60)
def get_user_by_id(user_id):
    """
    Get a user by ID.
    
    Args:
        user_id: ID of the user to retrieve
        
    Returns:
        User instance or None
    """
    try:
        return User.objects.select_related('profile').get(id=user_id)
    except User.DoesNotExist:
        return None


@cached_result('user_email', timeout=60)
def get_user_by_email(email):
    """
    Get a user by email.
    
    Args:
        email: Email of the user to retrieve
        
    Returns:
        User instance or None
    """
    try:
        return User.objects.select_related('profile').get(email=email)
    except User.DoesNotExist:
        return None


@cached_result('user_phone', timeout=60)
def get_user_by_phone(phone_number):
    """
    Get a user by phone number.
    
    Args:
        phone_number: Phone number of the user to retrieve
        
    Returns:
        User instance or None
    """
    try:
        return User.objects.select_related('profile').get(phone_number=phone_number)
    except User.DoesNotExist:
        return None


def get_users_by_type(user_type):
    """
    Get users by type.
    
    Args:
        user_type: Type of users to retrieve
        
    Returns:
        Queryset of users
    """
    return User.objects.filter(user_type=user_type, is_active=True)


def get_active_drivers():
    """
    Get all active drivers.
    
    Returns:
        Queryset of active drivers
    """
    return User.objects.filter(
        user_type='driver',
        is_active=True,
    ).select_related('profile')


def get_active_admins():
    """
    Get all active admins.
    
    Returns:
        Queryset of active admins
    """
    return User.objects.filter(
        user_type='admin',
        is_active=True,
    ).select_related('profile')


def get_users_with_fcm_tokens():
    """
    Get users with FCM tokens.
    
    Returns:
        Queryset of users with FCM tokens
    """
    return User.objects.filter(
        is_active=True,
        profile__fcm_token__isnull=False,
    ).exclude(
        profile__fcm_token=''
    ).select_related('profile')


def search_users(query, user_type=None):
    """
    Search users by name or email.
    
    Args:
        query: Search query
        user_type: Optional user type filter
        
    Returns:
        Queryset of matching users
    """
    queryset = User.objects.filter(
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(phone_number__icontains=query)
    )
    
    if user_type:
        queryset = queryset.filter(user_type=user_type)
    
    return queryset.select_related('profile')
