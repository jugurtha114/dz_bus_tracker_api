# Generated by Django 5.1.8 on 2025-04-16 16:28

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Bus",
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
                    "matricule",
                    models.CharField(
                        max_length=20, unique=True, verbose_name="matricule"
                    ),
                ),
                ("brand", models.CharField(max_length=50, verbose_name="brand")),
                ("model", models.CharField(max_length=50, verbose_name="model")),
                (
                    "year",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="year"
                    ),
                ),
                (
                    "capacity",
                    models.PositiveIntegerField(default=0, verbose_name="capacity"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
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
                    "last_maintenance",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last maintenance"
                    ),
                ),
                (
                    "next_maintenance",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="next maintenance"
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="metadata"),
                ),
            ],
            options={
                "verbose_name": "bus",
                "verbose_name_plural": "buses",
                "ordering": ["matricule"],
            },
        ),
        migrations.CreateModel(
            name="BusMaintenance",
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
                    "maintenance_type",
                    models.CharField(
                        choices=[
                            ("regular", "Regular"),
                            ("repair", "Repair"),
                            ("inspection", "Inspection"),
                            ("other", "Other"),
                        ],
                        max_length=50,
                        verbose_name="maintenance type",
                    ),
                ),
                ("date", models.DateTimeField(verbose_name="date")),
                ("description", models.TextField(verbose_name="description")),
                (
                    "cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="cost",
                    ),
                ),
                (
                    "performed_by",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="performed by"
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
            ],
            options={
                "verbose_name": "bus maintenance",
                "verbose_name_plural": "bus maintenances",
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="BusPhoto",
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
                    "photo",
                    models.ImageField(upload_to="bus_photos/", verbose_name="photo"),
                ),
                (
                    "photo_type",
                    models.CharField(
                        choices=[
                            ("exterior", "Exterior"),
                            ("interior", "Interior"),
                            ("document", "Document"),
                            ("other", "Other"),
                        ],
                        default="exterior",
                        max_length=50,
                        verbose_name="photo type",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="description"
                    ),
                ),
            ],
            options={
                "verbose_name": "bus photo",
                "verbose_name_plural": "bus photos",
                "ordering": ["bus", "photo_type"],
            },
        ),
        migrations.CreateModel(
            name="BusVerification",
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
                    "verification_date",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="verification date"
                    ),
                ),
                (
                    "rejection_reason",
                    models.TextField(blank=True, verbose_name="rejection reason"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
            ],
            options={
                "verbose_name": "bus verification",
                "verbose_name_plural": "bus verifications",
                "ordering": ["-created_at"],
            },
        ),
    ]
