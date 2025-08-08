#!/usr/bin/env python3
"""
Script to create test users for the DZ Bus Tracker system.
"""
import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.contrib.auth import get_user_model
from apps.drivers.models import Driver

User = get_user_model()

# Create driver user
email = "rachid.driver@dzbus.com"
password = "99999999."

try:
    # Try to get existing user
    user = User.objects.get(email=email)
    print(f"✅ User {email} already exists")
except User.DoesNotExist:
    # Create new user
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name="Rachid",
        last_name="Driver",
        user_type="DRIVER",
        is_active=True
    )
    print(f"✅ Created user: {email}")

# Ensure password is correct
user.set_password(password)
user.save()
print(f"✅ Password set for {email}")

# Create admin user
admin_email = "jugu@jugu.com"
admin_password = "99999999."

try:
    admin_user = User.objects.get(email=admin_email)
    print(f"✅ Admin user {admin_email} already exists")
except User.DoesNotExist:
    admin_user = User.objects.create_superuser(
        email=admin_email,
        password=admin_password,
        first_name="Jugu",
        last_name="Admin"
    )
    print(f"✅ Created admin user: {admin_email}")

# Ensure admin password is correct
admin_user.set_password(admin_password)
admin_user.save()
print(f"✅ Password set for {admin_email}")

print("\n🎉 Test users created successfully!")
print(f"Driver: {email} / {password}")
print(f"Admin: {admin_email} / {admin_password}")