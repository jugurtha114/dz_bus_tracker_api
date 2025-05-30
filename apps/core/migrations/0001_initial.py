# Generated by Django 5.2.1 on 2025-05-18 04:48

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Address',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('street', models.CharField(blank=True, max_length=255, verbose_name='street')),
                ('city', models.CharField(max_length=100, verbose_name='city')),
                ('state', models.CharField(max_length=100, verbose_name='state/wilaya')),
                ('postal_code', models.CharField(blank=True, max_length=20, verbose_name='postal code')),
                ('country', models.CharField(default='Algeria', max_length=100, verbose_name='country')),
                ('latitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='latitude')),
                ('longitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True, verbose_name='longitude')),
            ],
            options={
                'verbose_name': 'address',
                'verbose_name_plural': 'addresses',
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
    ]
