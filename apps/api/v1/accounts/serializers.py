"""
Serializers for the accounts API.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Profile, User
from apps.api.serializers import BaseSerializer, DynamicFieldsModelSerializer

User = get_user_model()


class ProfileSerializer(BaseSerializer):
    """
    Serializer for user profiles.
    """

    class Meta:
        model = Profile
        fields = [
            'id', 'avatar', 'bio', 'language',
            'push_notifications_enabled', 'email_notifications_enabled',
            'sms_notifications_enabled', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserSerializer(DynamicFieldsModelSerializer):
    """
    Serializer for users.
    """
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'user_type', 'is_active', 'date_joined', 'profile',
        ]
        read_only_fields = ['id', 'email', 'user_type', 'date_joined']
        extra_kwargs = {
            'password': {'write_only': True}
        }


class UserCreateSerializer(BaseSerializer):
    """
    Serializer for creating users.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'user_type', 'password', 'confirm_password',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        """
        Validate that passwords match.
        """
        if attrs['password'] != attrs.pop('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        return attrs

    def create(self, validated_data):
        """
        Create and return a new user with encrypted password.
        """
        from apps.accounts.services import UserService

        password = validated_data.pop('password')
        user = UserService.create_user(
            password=password,
            **validated_data
        )
        return user


class UserUpdateSerializer(BaseSerializer):
    """
    Serializer for updating users.
    """

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number',
        ]


class ProfileUpdateSerializer(BaseSerializer):
    """
    Serializer for updating profiles.
    """

    class Meta:
        model = Profile
        fields = [
            'avatar', 'bio', 'language',
            'push_notifications_enabled', 'email_notifications_enabled',
            'sms_notifications_enabled',
        ]


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for changing passwords.
    """
    current_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        """
        Validate that new password and confirm password match.
        """
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        return attrs

    def validate_current_password(self, value):
        """
        Validate that current password is correct.
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect')
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset.
    """
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming a password reset.
    """
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        """
        Validate that passwords match.
        """
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        return attrs