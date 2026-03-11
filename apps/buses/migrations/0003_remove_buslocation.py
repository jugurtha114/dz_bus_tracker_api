from django.db import migrations


class Migration(migrations.Migration):
    """
    Drop the BusLocation table as part of Phase 3 architectural cleanup.
    Bus location tracking is consolidated into apps/tracking/ (BusLocation in tracking app
    or Trip-based GPS storage). The buses.BusLocation model was a duplicate concern.
    """

    dependencies = [
        ('buses', '0002_bus_average_speed'),
    ]

    operations = [
        migrations.DeleteModel(name='BusLocation'),
    ]
