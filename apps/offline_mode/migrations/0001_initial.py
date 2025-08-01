# Generated by Django 5.2.1 on 2025-07-25 07:14

import django.contrib.postgres.fields
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
            name='CacheConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='configuration name')),
                ('is_active', models.BooleanField(default=True, verbose_name='is active')),
                ('cache_duration_hours', models.IntegerField(default=24, help_text='How long cached data remains valid', verbose_name='cache duration (hours)')),
                ('max_cache_size_mb', models.IntegerField(default=100, help_text='Maximum size of offline cache per user', verbose_name='max cache size (MB)')),
                ('cache_lines', models.BooleanField(default=True, verbose_name='cache lines data')),
                ('cache_stops', models.BooleanField(default=True, verbose_name='cache stops data')),
                ('cache_schedules', models.BooleanField(default=True, verbose_name='cache schedules data')),
                ('cache_buses', models.BooleanField(default=True, verbose_name='cache buses data')),
                ('cache_user_favorites', models.BooleanField(default=True, verbose_name='cache user favorites')),
                ('cache_notifications', models.BooleanField(default=True, verbose_name='cache notifications')),
                ('auto_sync_on_connect', models.BooleanField(default=True, verbose_name='auto sync on connection')),
                ('sync_interval_minutes', models.IntegerField(default=30, help_text='How often to sync when online', verbose_name='sync interval (minutes)')),
            ],
            options={
                'verbose_name': 'cache configuration',
                'verbose_name_plural': 'cache configurations',
            },
        ),
        migrations.CreateModel(
            name='UserCache',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_sync_at', models.DateTimeField(blank=True, null=True, verbose_name='last sync time')),
                ('cache_size_bytes', models.BigIntegerField(default=0, verbose_name='cache size (bytes)')),
                ('cache_version', models.CharField(default='1.0', max_length=20, verbose_name='cache version')),
                ('is_syncing', models.BooleanField(default=False, verbose_name='is syncing')),
                ('sync_progress', models.IntegerField(default=0, verbose_name='sync progress (%)')),
                ('last_error', models.TextField(blank=True, verbose_name='last sync error')),
                ('cached_lines_count', models.IntegerField(default=0, verbose_name='cached lines count')),
                ('cached_stops_count', models.IntegerField(default=0, verbose_name='cached stops count')),
                ('cached_schedules_count', models.IntegerField(default=0, verbose_name='cached schedules count')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='offline_cache', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'user cache',
                'verbose_name_plural': 'user caches',
            },
        ),
        migrations.CreateModel(
            name='OfflineLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('log_type', models.CharField(choices=[('sync_start', 'Sync Started'), ('sync_complete', 'Sync Completed'), ('sync_error', 'Sync Error'), ('cache_hit', 'Cache Hit'), ('cache_miss', 'Cache Miss'), ('cache_expired', 'Cache Expired'), ('cache_cleared', 'Cache Cleared'), ('offline_action', 'Offline Action')], max_length=30, verbose_name='log type')),
                ('message', models.TextField(verbose_name='message')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='metadata')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offline_logs', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'offline log',
                'verbose_name_plural': 'offline logs',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', '-created_at'], name='offline_mod_user_id_15a13e_idx'), models.Index(fields=['log_type', '-created_at'], name='offline_mod_log_typ_b33c30_idx')],
            },
        ),
        migrations.CreateModel(
            name='SyncQueue',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('create', 'Create'), ('update', 'Update'), ('delete', 'Delete')], max_length=20, verbose_name='action type')),
                ('model_name', models.CharField(max_length=100, verbose_name='model name')),
                ('object_id', models.CharField(blank=True, max_length=100, null=True, verbose_name='object ID')),
                ('data', models.JSONField(verbose_name='action data')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('syncing', 'Syncing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20, verbose_name='status')),
                ('attempts', models.IntegerField(default=0, verbose_name='sync attempts')),
                ('last_attempt_at', models.DateTimeField(blank=True, null=True, verbose_name='last attempt time')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='completed at')),
                ('error_message', models.TextField(blank=True, verbose_name='error message')),
                ('priority', models.IntegerField(default=0, help_text='Higher values are synced first', verbose_name='priority')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sync_queue', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'sync queue item',
                'verbose_name_plural': 'sync queue items',
                'ordering': ['-priority', 'created_at'],
                'indexes': [models.Index(fields=['user', 'status'], name='offline_mod_user_id_d3c6ae_idx'), models.Index(fields=['status', '-priority'], name='offline_mod_status_6db6db_idx')],
            },
        ),
        migrations.CreateModel(
            name='CachedData',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('data_type', models.CharField(choices=[('line', 'Line'), ('stop', 'Stop'), ('schedule', 'Schedule'), ('bus', 'Bus'), ('favorite', 'Favorite'), ('notification', 'Notification'), ('route', 'Route')], max_length=20, verbose_name='data type')),
                ('data_id', models.CharField(help_text='ID of the cached object', max_length=100, verbose_name='data ID')),
                ('data', models.JSONField(verbose_name='cached data')),
                ('size_bytes', models.IntegerField(default=0, verbose_name='size (bytes)')),
                ('checksum', models.CharField(blank=True, max_length=64, verbose_name='data checksum')),
                ('expires_at', models.DateTimeField(blank=True, null=True, verbose_name='expires at')),
                ('related_ids', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=100), blank=True, default=list, size=None, verbose_name='related data IDs')),
                ('user_cache', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cached_items', to='offline_mode.usercache', verbose_name='user cache')),
            ],
            options={
                'verbose_name': 'cached data',
                'verbose_name_plural': 'cached data',
                'indexes': [models.Index(fields=['user_cache', 'data_type'], name='offline_mod_user_ca_0b6ee4_idx'), models.Index(fields=['expires_at'], name='offline_mod_expires_af038c_idx')],
                'unique_together': {('user_cache', 'data_type', 'data_id')},
            },
        ),
    ]
