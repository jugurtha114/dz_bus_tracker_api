"""
Custom JWT views that use email for authentication.
"""
from rest_framework_simplejwt.views import TokenObtainPairView
from .jwt_serializers import EmailTokenObtainPairSerializer


class EmailTokenObtainPairView(TokenObtainPairView):
    """
    JWT token view that accepts email instead of username.
    """
    serializer_class = EmailTokenObtainPairSerializer