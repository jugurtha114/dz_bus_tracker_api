from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.base.api import BaseAPIView, BaseViewSet
from apps.core.base.permissions import IsOwnerOrAdmin
from .models import User, UserProfile
from .selectors import get_user_by_id
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserProfileSerializer,
    LoginSerializer,
    TokenSerializer,
    ChangePasswordSerializer,
    VerifyTokenSerializer,
)
from .services import (
    create_user,
    update_user,
    update_user_profile,
    send_verification_email,
    send_verification_sms,
    verify_email,
    verify_phone,
    generate_tokens,
    change_password,
    reset_password_request,
    reset_password,
    update_fcm_token,
    update_notification_preferences,
)


class UserViewSet(BaseViewSet):
    """
    API endpoint for users.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'reset_password', 'reset_password_request']:
            return [permissions.AllowAny()]
        elif self.action in ['update', 'partial_update', 'change_password', 'profile']:
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        return super().get_permissions()
    
    # def perform_create(self, serializer):
    #     create_user(serializer.validated_data)
    
    def perform_update(self, serializer):
        update_user(self.get_object(), serializer.validated_data)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        success = change_password(
            request.user,
            serializer.validated_data['current_password'],
            serializer.validated_data['new_password'],
        )
        
        if success:
            return Response({'detail': 'Password changed successfully.'})
        
        return Response(
            {'detail': 'Failed to change password.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def reset_password_request(self, request):
        email = request.data.get('email')
        if not email:
            return Response(
                {'detail': 'Email is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success = reset_password_request(email)
        
        return Response({'detail': 'Password reset email sent if account exists.'})
    
    @action(detail=False, methods=['post'])
    def reset_password(self, request):
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        if not token or not new_password or not confirm_password:
            return Response(
                {'detail': 'Token, new password, and confirm password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_password != confirm_password:
            return Response(
                {'detail': 'Passwords do not match.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = reset_password(token, new_password)
        
        if not user:
            return Response(
                {'detail': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({'detail': 'Password reset successfully.'})
    
    @action(detail=False, methods=['post'])
    def resend_verification_email(self, request):
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        success = send_verification_email(request.user)
        
        if success:
            return Response({'detail': 'Verification email sent.'})
        
        return Response(
            {'detail': 'Failed to send verification email.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @action(detail=False, methods=['post'])
    def verify_email(self, request):
        serializer = VerifyTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token = serializer.validated_data['token']
        user = verify_email(token)
        
        if not user:
            return Response(
                {'detail': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({'detail': 'Email verified successfully.'})
    
    @action(detail=False, methods=['post'])
    def send_phone_verification(self, request):
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not request.user.phone_number:
            return Response(
                {'detail': 'Phone number is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success = send_verification_sms(request.user)
        
        if success:
            return Response({'detail': 'Verification SMS sent.'})
        
        return Response(
            {'detail': 'Failed to send verification SMS.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @action(detail=False, methods=['post'])
    def verify_phone(self, request):
        serializer = VerifyTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token = serializer.validated_data['token']
        user = verify_phone(token)
        
        if not user:
            return Response(
                {'detail': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({'detail': 'Phone verified successfully.'})
    
    @action(detail=False, methods=['get', 'put', 'patch'])
    def profile(self, request):
        if request.method == 'GET':
            user = request.user
            profile = user.profile
            serializer = UserSerializer(user)
            return Response(serializer.data)
        
        profile = request.user.profile
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_user_profile(request.user, serializer.validated_data)

        # user_serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def fcm_token(self, request):
        fcm_token = request.data.get('fcm_token')
        
        if not fcm_token:
            return Response(
                {'detail': 'FCM token is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        profile = update_fcm_token(request.user, fcm_token)
        serializer = UserProfileSerializer(profile)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['put', 'patch'])
    def notification_preferences(self, request):
        preferences = request.data
        
        if not preferences:
            return Response(
                {'detail': 'Notification preferences are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        profile = update_notification_preferences(request.user, preferences)
        serializer = UserProfileSerializer(profile)
        
        return Response(serializer.data)


class LoginAPIView(BaseAPIView):
    """
    API endpoint for user login.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        token_serializer = TokenSerializer(
            data=generate_tokens(user),
            context={'request': request}
        )
        token_serializer.is_valid(raise_exception=True)
        
        data = token_serializer.initial_data
        data['user'] = UserSerializer(user, context={'request': request}).data
        
        return Response(data)


class TokenRefreshAPIView(TokenRefreshView):
    """
    API endpoint for refreshing tokens.
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        # Include user data in response
        if 'access' in response.data and request.user.is_authenticated:
            response.data['user'] = UserSerializer(
                request.user,
                context={'request': request}
            ).data
        
        return response
