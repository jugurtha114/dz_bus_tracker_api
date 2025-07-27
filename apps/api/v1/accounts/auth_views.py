"""
Authentication views for the accounts API.
"""
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import UserService
from .serializers import UserCreateSerializer, UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new user.
    """
    serializer = UserCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    user = serializer.save()
    
    # Generate tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'user': UserSerializer(user).data,
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Login a user.
    """
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response({
            'error': 'Please provide both email and password'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Try to authenticate with email
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        # Get user by email
        user_obj = User.objects.get(email=email)
        # Authenticate with username (which might be different from email)
        user = authenticate(request, username=user_obj.email, password=password)
    except User.DoesNotExist:
        user = None
    
    if not user:
        return Response({
            'error': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if not user.is_active:
        return Response({
            'error': 'Account is disabled'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Generate tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'user': UserSerializer(user).data,
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def register_driver(request):
    """
    Register a new driver with their driver information.
    """
    from apps.drivers.serializers import DriverRegistrationSerializer
    from apps.drivers.models import Driver
    
    serializer = DriverRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    # Create user
    user_data = {
        'email': serializer.validated_data['email'],
        'password': serializer.validated_data['password'],
        'first_name': serializer.validated_data['first_name'],
        'last_name': serializer.validated_data['last_name'],
        'phone_number': serializer.validated_data['phone_number'],
        'user_type': 'driver',
    }
    
    user = UserService.create_user(**user_data)
    
    # Create driver profile
    driver_data = {
        'user': user,
        'phone_number': serializer.validated_data['phone_number'],
        'id_card_number': serializer.validated_data['id_card_number'],
        'id_card_photo': serializer.validated_data['id_card_photo'],
        'driver_license_number': serializer.validated_data['driver_license_number'],
        'driver_license_photo': serializer.validated_data['driver_license_photo'],
        'years_of_experience': serializer.validated_data['years_of_experience'],
    }
    
    driver = Driver.objects.create(**driver_data)
    
    # Generate tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'user': UserSerializer(user).data,
        'driver_id': str(driver.id),
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }, status=status.HTTP_201_CREATED)