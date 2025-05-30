# Generated by Django 5.2.1 on 2025-05-18 04:48

import apps.core.utils.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('drivers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Bus',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('license_plate', models.CharField(max_length=15, unique=True, validators=[apps.core.utils.validators.validate_plate_number], verbose_name='license plate')),
                ('model', models.CharField(max_length=100, verbose_name='model')),
                ('manufacturer', models.CharField(max_length=100, verbose_name='manufacturer')),
                ('year', models.PositiveSmallIntegerField(verbose_name='year')),
                ('capacity', models.PositiveSmallIntegerField(help_text='Maximum number of passengers', verbose_name='capacity')),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('maintenance', 'Maintenance')], default='active', max_length=20, verbose_name='status')),
                ('is_air_conditioned', models.BooleanField(default=False, verbose_name='air conditioned')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='buses/', verbose_name='photo')),
                ('features', models.JSONField(blank=True, default=list, help_text='Additional features of the bus', verbose_name='features')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('is_approved', models.BooleanField(default=False, verbose_name='approved')),
                ('driver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='buses', to='drivers.driver', verbose_name='driver')),
            ],
            options={
                'verbose_name': 'bus',
                'verbose_name_plural': 'buses',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BusLocation',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('latitude', models.DecimalField(decimal_places=7, max_digits=10, verbose_name='latitude')),
                ('longitude', models.DecimalField(decimal_places=7, max_digits=10, verbose_name='longitude')),
                ('altitude', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='altitude')),
                ('speed', models.DecimalField(blank=True, decimal_places=2, help_text='Speed in km/h', max_digits=5, null=True, verbose_name='speed')),
                ('heading', models.DecimalField(blank=True, decimal_places=2, help_text='Heading in degrees (0-360)', max_digits=5, null=True, verbose_name='heading')),
                ('accuracy', models.DecimalField(blank=True, decimal_places=2, help_text='Accuracy in meters', max_digits=5, null=True, verbose_name='accuracy')),
                ('is_tracking_active', models.BooleanField(default=True, verbose_name='tracking active')),
                ('passenger_count', models.PositiveSmallIntegerField(default=0, verbose_name='passenger count')),
                ('bus', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='locations', to='buses.bus', verbose_name='bus')),
            ],
            options={
                'verbose_name': 'bus location',
                'verbose_name_plural': 'bus locations',
                'ordering': ['-created_at'],
                'get_latest_by': 'created_at',
            },
        ),
    ]
