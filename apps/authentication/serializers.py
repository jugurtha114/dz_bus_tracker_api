from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
# from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.base.serializers import BaseModelSerializer
from .models import User, UserProfile, VerificationToken


class UserProfileSerializer(BaseModelSerializer):
    """
    Serializer for UserProfile model.
    """
    class Meta:
        model = UserProfile
        fields = ['id', 'profile_picture', 'notification_preferences', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserSerializer(BaseModelSerializer):
    """
    Serializer for User model.
    """
    profile = UserProfileSerializer(read_only=True)
    # phone_number = PhoneNumberField(required=False, allow_null=True, allow_blank=True)
    # phone_number = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=20)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'user_type', 'language', 'is_active', 'is_email_verified',
            'is_phone_verified', 'profile', 'date_joined', 'last_login',
        ]
        read_only_fields = [
            'id', 'is_active', 'is_email_verified', 'is_phone_verified',
            'date_joined', 'last_login',
        ]


class UserCreateSerializer(BaseModelSerializer):
    """
    Serializer for creating a new user.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    profile = UserProfileSerializer(read_only=True)
    # phone_number = PhoneNumberField(required=False, allow_null=True, allow_blank=True)
    # phone_number = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=20)
    
    class Meta:
        model = User
        # fields = [
        #     'id', 'email', 'password', 'confirm_password', 'first_name', 'last_name',
        #     'phone_number', 'user_type', 'language', 'id', 'is_active', 'is_email_verified', 'is_phone_verified',
        #     'date_joined', 'last_login',
        # ]
        fields = '__all__'
        read_only_fields = ['id', 'is_active', 'is_email_verified', 'is_phone_verified',
            'date_joined', 'last_login',
        ]
    
    def validate(self, attrs):
        """
        Validate the password and confirm_password fields.
        """
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({'confirm_password': _('Passwords do not match.')})
        
        return attrs
    
    def create(self, validated_data):
        """
        Create and return a new user.
        """
        # Remove confirm_password from validated data
        validated_data.pop('confirm_password', None)

        # Create user
        user = User.objects.create_user(**validated_data)

        # Create user profile
        UserProfile.objects.create(user=user)
        
        return user


class UserUpdateSerializer(BaseModelSerializer):
    """
    Serializer for updating a user.
    """
    # phone_number = PhoneNumberField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=20)
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'language',
        ]
    
    def update(self, instance, validated_data):
        """
        Update and return a user.
        """
        # Phone number verification reset if changed
        if 'phone_number' in validated_data and validated_data['phone_number'] != instance.phone_number:
            instance.is_phone_verified = False
        
        # Update user
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing a user's password.
    """
    current_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(required=True, style={'input_type': 'password'})
    
    def validate(self, attrs):
        """
        Validate the current_password and new_password fields.
        """
        # Get user
        user = self.context['request'].user
        
        # Check current password
        if not user.check_password(attrs.get('current_password')):
            raise serializers.ValidationError({'current_password': _('Current password is incorrect.')})
        
        # Check new password
        if attrs.get('new_password') != attrs.get('confirm_new_password'):
            raise serializers.ValidationError({'confirm_new_password': _('Passwords do not match.')})
        
        return attrs
    
    def update(self, instance, validated_data):
        """
        Update and return a user's password.
        """
        # Set new password
        instance.set_password(validated_data['new_password'])
        instance.save(update_fields=['password'])
        
        return instance


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, style={'input_type': 'password'})
    
    def validate(self, attrs):
        """
        Validate the email and password fields.
        """
        # Authenticate user
        user = authenticate(
            request=self.context.get('request'),
            email=attrs.get('email'),
            password=attrs.get('password')
        )
        
        # Check if authentication succeeded
        if not user:
            raise serializers.ValidationError(_('Invalid email or password.'))
        
        # Check if user is active
        if not user.is_active:
            raise serializers.ValidationError(_('User account is disabled.'))
        
        # Add user to validated data
        attrs['user'] = user
        
        return attrs


class TokenSerializer(serializers.Serializer):
    """
    Serializer for JWT tokens.
    """
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)
    
    def create(self, validated_data):
        """
        Create and return a new token pair.
        """
        # Get user
        user = validated_data.get('user')
        
        # Generate token
        refresh = RefreshToken.for_user(user)
        
        # Update last login
        user.save(update_fields=['last_login'])
        
        # Return token pair and user
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': user,
        }


class VerificationTokenSerializer(BaseModelSerializer):
    """
    Serializer for VerificationToken model.
    """
    class Meta:
        model = VerificationToken
        fields = ['id', 'token', 'token_type', 'expires_at', 'is_used', 'created_at']
        read_only_fields = ['id', 'token', 'expires_at', 'is_used', 'created_at']


class VerifyTokenSerializer(serializers.Serializer):
    """
    Serializer for verifying a token.
    """
    token = serializers.CharField(required=True)
    
    def validate(self, attrs):
        """
        Validate the token.
        """
        # Get token
        token = attrs.get('token')
        
        # Find token in database
        try:
            verification_token = VerificationToken.objects.get(token=token, is_used=False)
        except VerificationToken.DoesNotExist:
            raise serializers.ValidationError(_('Invalid or expired token.'))
        
        # Check if token is expired
        if verification_token.is_expired:
            raise serializers.ValidationError(_('Token has expired.'))
        
        # Add verification token to validated data
        attrs['verification_token'] = verification_token
        
        return attrs