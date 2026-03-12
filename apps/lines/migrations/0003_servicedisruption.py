import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('lines', '0002_stop_wilaya_commune_line_fare_dza'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceDisruption',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('disruption_type', models.CharField(
                    choices=[
                        ('suspension', 'Service Suspension'),
                        ('delay', 'Major Delay'),
                        ('diversion', 'Route Diversion'),
                        ('other', 'Other'),
                    ],
                    max_length=20,
                    verbose_name='disruption type',
                )),
                ('title', models.CharField(max_length=200, verbose_name='title')),
                ('description', models.TextField(verbose_name='description')),
                ('start_time', models.DateTimeField(verbose_name='start time')),
                ('end_time', models.DateTimeField(blank=True, null=True, verbose_name='end time')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('line', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='disruptions',
                    to='lines.line',
                    verbose_name='line',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_disruptions',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='created by',
                )),
            ],
            options={
                'verbose_name': 'service disruption',
                'verbose_name_plural': 'service disruptions',
                'ordering': ['-created_at'],
            },
        ),
    ]
