"""
Management command to create development users for local Docker environment.
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.constants import (
    USER_TYPE_ADMIN,
    USER_TYPE_DRIVER,
    USER_TYPE_PASSENGER,
)

DEV_PASSWORD = "Green+114"

DEV_USERS = [
    {
        "email": "driver@dzbus.com",
        "user_type": USER_TYPE_DRIVER,
        "first_name": "Dev",
        "last_name": "Driver",
        "is_superuser": False,
    },
    {
        "email": "passenger@dzbus.com",
        "user_type": USER_TYPE_PASSENGER,
        "first_name": "Dev",
        "last_name": "Passenger",
        "is_superuser": False,
    },
    {
        "email": "admin@dzbus.com",
        "user_type": USER_TYPE_ADMIN,
        "first_name": "Dev",
        "last_name": "Admin",
        "is_superuser": True,
    },
]


class Command(BaseCommand):
    help = "Create development users (driver, passenger, admin) for local Docker environment."

    def handle(self, *args, **options):
        for user_data in DEV_USERS:
            email = user_data["email"]

            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f"  [{user_data['user_type']}] {email} already exists — skipped"))
                continue

            if user_data["is_superuser"]:
                User.objects.create_superuser(
                    email=email,
                    password=DEV_PASSWORD,
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                )
            else:
                User.objects.create_user(
                    email=email,
                    password=DEV_PASSWORD,
                    user_type=user_data["user_type"],
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                )

            self.stdout.write(self.style.SUCCESS(f"  [{user_data['user_type']}] {email} created"))

        self.stdout.write(self.style.SUCCESS("Dev user seeding complete."))
