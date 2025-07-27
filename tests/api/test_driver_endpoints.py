#!/usr/bin/env python3
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.drivers.models import Driver

User = get_user_model()
client = APIClient()

# Get admin user
admin = User.objects.filter(email='admin@dzbus.com').first()
client.force_authenticate(user=admin)

# Get pending driver
driver = Driver.objects.filter(status='pending').first()
if driver:
    # Try different endpoint patterns
    endpoints = [
        f'/api/v1/drivers/{driver.id}/',
        f'/api/v1/drivers/drivers/{driver.id}/',
    ]
    
    for endpoint in endpoints:
        response = client.patch(endpoint, {'status': 'approved'}, format='json')
        print(f'{endpoint}: {response.status_code}')
        if response.status_code != 404:
            print(f'Response: {response.data}')