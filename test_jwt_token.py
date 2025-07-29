#!/usr/bin/env python3
"""
Test script to validate JWT token and user.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()

# The token from the log
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzUzNzk5MDE1LCJpYXQiOjE3NTM3OTcyMTUsImp0aSI6IjdmMzRhNDMxM2ZhNTRkMjBhZDM5ZTQwNGM3ZGZkN2UzIiwidXNlcl9pZCI6IjkwZDVkOTc0LWFlMzItNDg0Mi1hMTViLTU1YTIwNWRkNjdiNyJ9.PX1PTBRHLFw1D8DR8POmhSPlijWoNPF4jWMpqRNqC-M"

try:
    # Validate the token
    print("Validating JWT token...")
    validated_token = UntypedToken(token)
    print(f"Token is valid!")
    print(f"Token payload: {validated_token.payload}")
    
    # Get user ID
    user_id = validated_token['user_id']
    print(f"User ID from token: {user_id}")
    
    # Try to get user
    try:
        user = User.objects.get(id=user_id)
        print(f"User found: {user.email} (Active: {user.is_active})")
    except User.DoesNotExist:
        print(f"User with ID {user_id} not found in database")
        
except (InvalidToken, TokenError) as e:
    print(f"Token validation failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")