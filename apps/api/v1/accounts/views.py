"""
Views for the accounts API.
"""
from django.contrib.auth import get_user_model
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Profile
from apps.accounts.services import UserService, ProfileService
from apps.api.viewsets import BaseModelViewSet, ReadOnlyModelViewSet
from apps.core.permissions import IsOwnerOrReadOnly

from .serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

User = get_user_model()


class UserViewSet(BaseModelViewSet):
    """
    API endpoint for users.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    service_class = UserService

    def get_queryset(self):
        """
        Filter users based on user type.
        """
        queryset = super().get_queryset()

        # Regular users can only see themselves
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            return queryset.filter(id=user.id)

        # Admins can see all users or filter by type
        user_type = self.request.query_params.get('user_type')
        if user_type:
            queryset = queryset.filter(user_type=user_type)

        return queryset

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action == 'me':
            return [IsAuthenticated()]
        if self.action in ['create', 'reset_password_request', 'reset_password_confirm']:
            return [AllowAny()]
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'change_password']:
            return [IsAuthenticated(), IsOwnerOrReadOnly()]
        return [IsAdminUser()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        if self.action == 'change_password':
            return PasswordChangeSerializer
        if self.action == 'reset_password_request':
            return PasswordResetRequestSerializer
        if self.action == 'reset_password_confirm':
            return PasswordResetConfirmSerializer
        return UserSerializer

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        """
        Change user password.
        """
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        UserService.update_user_password(
            user_id=user.id,
            password=serializer.validated_data['new_password']
        )

        return Response({'detail': 'Password changed successfully'})

    @action(detail=False, methods=['post'])
    def reset_password_request(self, request):
        """
        Request a password reset.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
            # Generate token and send email
            token_data = UserService.generate_password_reset_token(user)
            # TODO: Send email with token
        except User.DoesNotExist:
            # Don't reveal that the user doesn't exist
            pass

        return Response({'detail': 'Password reset email sent if account exists'})

    @action(detail=False, methods=['post'])
    def reset_password_confirm(self, request):
        """
        Confirm a password reset.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
            user = User.objects.get(pk=uid)

            # Verify token
            from django.contrib.auth.tokens import default_token_generator
            if not default_token_generator.check_token(user, serializer.validated_data['token']):
                return Response(
                    {'detail': 'Invalid or expired token'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update password
            UserService.update_user_password(
                user_id=user.id,
                password=serializer.validated_data['new_password']
            )

            return Response({'detail': 'Password reset successful'})

        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'detail': 'Invalid reset link'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Get the current user.
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def logout(self, request):
        """
        Invalidate the refresh token.
        """
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'detail': 'Logout successful'})
        except Exception:
            return Response({'detail': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


class ProfileViewSet(BaseModelViewSet):
    """
    API endpoint for profiles.
    """
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    service_class = ProfileService

    def get_queryset(self):
        """
        Filter profiles based on user type.
        """
        queryset = super().get_queryset()

        # Regular users can only see themselves
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            return queryset.filter(user_id=user.id)

        return queryset

    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['me', 'update_me', 'update_notification_preferences']:
            return [IsAuthenticated()]
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsOwnerOrReadOnly()]
        return [IsAdminUser()]

    def get_serializer_class(self):
        """
        Get serializer based on action.
        """
        if self.action in ['update', 'partial_update']:
            return ProfileUpdateSerializer
        return ProfileSerializer

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Get the current user's profile.
        """
        profile = request.user.profile
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_me(self, request):
        """
        Update the current user's profile.
        """
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        ProfileService.update_profile(
            user_id=request.user.id,
            **serializer.validated_data
        )

        updated_serializer = self.get_serializer(profile)
        return Response(updated_serializer.data)

    @action(detail=False, methods=['patch'])
    def update_notification_preferences(self, request):
        """
        Update notification preferences.
        """
        profile = request.user.profile

        # Extract only notification preference fields
        notification_prefs = {
            k: v for k, v in request.data.items()
            if k in [
                'push_notifications_enabled',
                'email_notifications_enabled',
                'sms_notifications_enabled',
            ]
        }

        ProfileService.update_notification_preferences(
            user_id=request.user.id,
            **notification_prefs
        )

        serializer = self.get_serializer(profile)
        return Response(serializer.data)