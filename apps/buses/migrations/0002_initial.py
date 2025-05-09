# Generated by Django 5.1.8 on 2025-04-16 16:28

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("buses", "0001_initial"),
        ("drivers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="bus",
            name="driver",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="buses",
                to="drivers.driver",
                verbose_name="driver",
            ),
        ),
        migrations.AddField(
            model_name="busmaintenance",
            name="bus",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="maintenance_records",
                to="buses.bus",
                verbose_name="bus",
            ),
        ),
        migrations.AddField(
            model_name="busphoto",
            name="bus",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="photos",
                to="buses.bus",
                verbose_name="bus",
            ),
        ),
        migrations.AddField(
            model_name="busverification",
            name="bus",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="verifications",
                to="buses.bus",
                verbose_name="bus",
            ),
        ),
        migrations.AddField(
            model_name="busverification",
            name="verified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bus_verifications",
                to=settings.AUTH_USER_MODEL,
                verbose_name="verified by",
            ),
        ),
        migrations.AddIndex(
            model_name="bus",
            index=models.Index(fields=["driver"], name="buses_bus_driver__83028b_idx"),
        ),
        migrations.AddIndex(
            model_name="bus",
            index=models.Index(
                fields=["matricule"], name="buses_bus_matricu_70be44_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bus",
            index=models.Index(
                fields=["is_verified"], name="buses_bus_is_veri_e67aa4_idx"
            ),
        ),
    ]
