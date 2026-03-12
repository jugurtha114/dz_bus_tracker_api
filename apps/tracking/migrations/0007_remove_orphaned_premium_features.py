"""
Data migration: remove PremiumFeature and UserPremiumFeature rows whose
feature_type was removed from FEATURE_TYPES choices in migration 0005.
"""
from django.db import migrations

# Matches the current FEATURE_TYPES in tracking/models.py
VALID_FEATURE_TYPES = {
    'route_analytics',
    'performance_insights',
    'passenger_feedback',
    'priority_support',
    'custom_dashboard',
}


def remove_orphaned_premium_features(apps, schema_editor):
    PremiumFeature = apps.get_model('tracking', 'PremiumFeature')
    UserPremiumFeature = apps.get_model('tracking', 'UserPremiumFeature')

    orphaned = PremiumFeature.objects.exclude(feature_type__in=VALID_FEATURE_TYPES)
    UserPremiumFeature.objects.filter(feature__in=orphaned).delete()
    orphaned.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0006_anomaly_reported_by'),
    ]

    operations = [
        migrations.RunPython(
            remove_orphaned_premium_features,
            migrations.RunPython.noop,
        ),
    ]
