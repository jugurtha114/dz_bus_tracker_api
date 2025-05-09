# Generated by Django 5.1.8 on 2025-04-16 16:28

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("lines", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Passenger",
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
                    "journey_count",
                    models.PositiveIntegerField(
                        default=0, verbose_name="journey count"
                    ),
                ),
                (
                    "notification_preferences",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="notification preferences",
                    ),
                ),
                (
                    "home_location",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="home location"
                    ),
                ),
                (
                    "work_location",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="work location"
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="passenger_profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "passenger",
                "verbose_name_plural": "passengers",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SavedLocation",
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
                ("name", models.CharField(max_length=100, verbose_name="name")),
                (
                    "latitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9, verbose_name="latitude"
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9, verbose_name="longitude"
                    ),
                ),
                (
                    "address",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="address"
                    ),
                ),
                (
                    "is_favorite",
                    models.BooleanField(default=False, verbose_name="favorite"),
                ),
                (
                    "passenger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_locations",
                        to="passengers.passenger",
                        verbose_name="passenger",
                    ),
                ),
            ],
            options={
                "verbose_name": "saved location",
                "verbose_name_plural": "saved locations",
                "ordering": ["-is_favorite", "name"],
            },
        ),
        migrations.CreateModel(
            name="TripHistory",
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
                ("start_time", models.DateTimeField(verbose_name="start time")),
                (
                    "end_time",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="end time"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("started", "Started"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="started",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                (
                    "end_stop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trip_ends",
                        to="lines.stop",
                        verbose_name="end stop",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="passenger_trips",
                        to="lines.line",
                        verbose_name="line",
                    ),
                ),
                (
                    "passenger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trip_history",
                        to="passengers.passenger",
                        verbose_name="passenger",
                    ),
                ),
                (
                    "start_stop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trip_starts",
                        to="lines.stop",
                        verbose_name="start stop",
                    ),
                ),
            ],
            options={
                "verbose_name": "trip history",
                "verbose_name_plural": "trip histories",
                "ordering": ["-start_time"],
            },
        ),
        migrations.CreateModel(
            name="FeedbackRequest",
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
                    "sent_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="sent at"),
                ),
                ("expires_at", models.DateTimeField(verbose_name="expires at")),
                (
                    "is_completed",
                    models.BooleanField(default=False, verbose_name="completed"),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedback_requests",
                        to="lines.line",
                        verbose_name="line",
                    ),
                ),
                (
                    "passenger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedback_requests",
                        to="passengers.passenger",
                        verbose_name="passenger",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedback_requests",
                        to="passengers.triphistory",
                        verbose_name="trip",
                    ),
                ),
            ],
            options={
                "verbose_name": "feedback request",
                "verbose_name_plural": "feedback requests",
                "ordering": ["-sent_at"],
            },
        ),
    ]
