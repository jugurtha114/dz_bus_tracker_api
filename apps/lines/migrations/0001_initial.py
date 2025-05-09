# Generated by Django 5.1.8 on 2025-04-16 16:28

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("buses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Stop",
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
                    "latitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9, verbose_name="Latitude"
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        decimal_places=6, max_digits=9, verbose_name="Longitude"
                    ),
                ),
                (
                    "accuracy",
                    models.FloatField(
                        blank=True, null=True, verbose_name="Accuracy (meters)"
                    ),
                ),
                ("name", models.CharField(max_length=100, verbose_name="name")),
                (
                    "code",
                    models.CharField(blank=True, max_length=20, verbose_name="code"),
                ),
                (
                    "address",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="address"
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="stop_images/",
                        verbose_name="image",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="metadata"),
                ),
            ],
            options={
                "verbose_name": "stop",
                "verbose_name_plural": "stops",
                "ordering": ["name"],
                "indexes": [
                    models.Index(fields=["name"], name="lines_stop_name_106112_idx"),
                    models.Index(fields=["code"], name="lines_stop_code_d4ee41_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Line",
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
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "color",
                    models.CharField(
                        default="#3498db", max_length=7, verbose_name="color"
                    ),
                ),
                (
                    "path",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="GeoJSON representation of the line path",
                        verbose_name="path",
                    ),
                ),
                (
                    "estimated_duration",
                    models.PositiveIntegerField(
                        default=0, verbose_name="estimated duration (minutes)"
                    ),
                ),
                (
                    "distance",
                    models.FloatField(default=0, verbose_name="distance (meters)"),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="metadata"),
                ),
                (
                    "end_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines_ending",
                        to="lines.stop",
                        verbose_name="end location",
                    ),
                ),
                (
                    "start_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines_starting",
                        to="lines.stop",
                        verbose_name="start location",
                    ),
                ),
            ],
            options={
                "verbose_name": "line",
                "verbose_name_plural": "lines",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Favorite",
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
                    "notification_threshold",
                    models.PositiveIntegerField(
                        default=5,
                        help_text="Notify when bus is this many minutes away",
                        verbose_name="notification threshold (minutes)",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorites",
                        to="lines.line",
                        verbose_name="line",
                    ),
                ),
            ],
            options={
                "verbose_name": "favorite",
                "verbose_name_plural": "favorites",
                "ordering": ["user", "line"],
                "unique_together": {("user", "line")},
            },
        ),
        migrations.CreateModel(
            name="LineBus",
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
                    "is_primary",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this is the primary line for this bus",
                        verbose_name="primary",
                    ),
                ),
                (
                    "bus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_buses",
                        to="buses.bus",
                        verbose_name="bus",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_buses",
                        to="lines.line",
                        verbose_name="line",
                    ),
                ),
            ],
            options={
                "verbose_name": "line bus",
                "verbose_name_plural": "line buses",
                "ordering": ["line", "bus"],
                "unique_together": {("line", "bus")},
            },
        ),
        migrations.CreateModel(
            name="LineStop",
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
                ("order", models.PositiveIntegerField(default=0, verbose_name="order")),
                (
                    "distance_from_start",
                    models.FloatField(
                        default=0, verbose_name="distance from start (meters)"
                    ),
                ),
                (
                    "estimated_time_from_start",
                    models.PositiveIntegerField(
                        default=0, verbose_name="estimated time from start (seconds)"
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_stops",
                        to="lines.line",
                        verbose_name="line",
                    ),
                ),
                (
                    "stop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_stops",
                        to="lines.stop",
                        verbose_name="stop",
                    ),
                ),
            ],
            options={
                "verbose_name": "line stop",
                "verbose_name_plural": "line stops",
                "ordering": ["line", "order"],
                "indexes": [
                    models.Index(
                        fields=["line", "order"], name="lines_lines_line_id_5699b7_idx"
                    )
                ],
                "unique_together": {("line", "order"), ("line", "stop")},
            },
        ),
        migrations.AddIndex(
            model_name="line",
            index=models.Index(fields=["name"], name="lines_line_name_82efd3_idx"),
        ),
        migrations.AddIndex(
            model_name="line",
            index=models.Index(
                fields=["start_location"], name="lines_line_start_l_994e39_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="line",
            index=models.Index(
                fields=["end_location"], name="lines_line_end_loc_ec5b2a_idx"
            ),
        ),
    ]
