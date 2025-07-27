"""
Custom authentication backend for email-based authentication.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Authenticate using email address instead of username.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Override the authenticate method to allow users to log in using their email address.
        """
        # Try to get email from kwargs first (for explicit email parameter)
        email = kwargs.get('email', username)
        
        if email is None:
            return None
        
        try:
            # Try to fetch the user by email
            user = User.objects.get(email=email)
            
            # Check the password
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            User().set_password(password)
            
        return None
    
    def get_user(self, user_id):
        """
        Get a user by their ID.
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None