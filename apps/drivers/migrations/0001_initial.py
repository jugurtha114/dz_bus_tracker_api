# Generated by Django 5.1.8 on 2025-04-16 16:28

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Driver",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="Created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "is_deleted",
                    models.BooleanField(default=False, verbose_name="Deleted"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Deleted at"
                    ),
                ),
                (
                    "id_number",
                    models.CharField(
                        max_length=50, unique=True, verbose_name="ID number"
                    ),
                ),
                (
                    "id_photo",
                    models.ImageField(upload_to="driver_ids/", verbose_name="ID photo"),
                ),
                (
                    "license_number",
                    models.CharField(
                        max_length=50, unique=True, verbose_name="license number"
                    ),
                ),
                (
                    "license_photo",
                    models.ImageField(
                        upload_to="driver_licenses/", verbose_name="license photo"
                    ),
                ),
                (
                    "is_verified",
                    models.BooleanField(default=False, verbose_name="verified"),
                ),
                (
                    "verification_date",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="verification date"
                    ),
                ),
                (
                    "experience_years",
                    models.PositiveIntegerField(
                        default=0, verbose_name="experience years"
                    ),
                ),
                (
                    "date_of_birth",
                    models.DateField(
                        blank=True, null=True, verbose_name="date of birth"
                    ),
                ),
                ("address", models.TextField(blank=True, verbose_name="address")),
                (
                    "emergency_contact",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="emergency contact"
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="metadata"),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "driver",
                "verbose_name_plural": "drivers",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DriverApplication",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="Created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "is_deleted",
                    models.BooleanField(default=False, verbose_name="Deleted"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Deleted at"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="reviewed at"
                    ),
                ),
                (
                    "rejection_reason",
                    models.TextField(blank=True, verbose_name="rejection reason"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="metadata"),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="applications",
                        to="drivers.driver",
                        verbose_name="driver",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_driver_applications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="reviewed by",
                    ),
                ),
            ],
            options={
                "verbose_name": "driver application",
                "verbose_name_plural": "driver applications",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DriverRating",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="Created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "is_deleted",
                    models.BooleanField(default=False, verbose_name="Deleted"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Deleted at"
                    ),
                ),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "1 - Poor"),
                            (2, "2 - Below Average"),
                            (3, "3 - Average"),
                            (4, "4 - Good"),
                            (5, "5 - Excellent"),
                        ],
                        verbose_name="rating",
                    ),
                ),
                ("comment", models.TextField(blank=True, verbose_name="comment")),
                (
                    "is_anonymous",
                    models.BooleanField(default=False, verbose_name="anonymous"),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ratings",
                        to="drivers.driver",
                        verbose_name="driver",
                    ),
                ),
                (
                    "passenger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_ratings",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="passenger",
                    ),
                ),
            ],
            options={
                "verbose_name": "driver rating",
                "verbose_name_plural": "driver ratings",
                "ordering": ["-created_at"],
            },
        ),
    ]
