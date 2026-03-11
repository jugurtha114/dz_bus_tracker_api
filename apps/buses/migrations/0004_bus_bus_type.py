from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buses', '0003_remove_buslocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='bus',
            name='bus_type',
            field=models.CharField(
                choices=[
                    ('microbus', 'Microbus'),
                    ('city_bus', 'City Bus'),
                    ('articulated', 'Articulated Bus'),
                    ('minibus', 'Minibus'),
                ],
                default='city_bus',
                max_length=20,
                verbose_name='bus type',
            ),
        ),
    ]
