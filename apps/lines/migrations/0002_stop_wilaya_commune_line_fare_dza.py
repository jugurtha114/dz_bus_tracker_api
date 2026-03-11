from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lines', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stop',
            name='wilaya',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='wilaya'),
        ),
        migrations.AddField(
            model_name='stop',
            name='commune',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='commune'),
        ),
        migrations.AddField(
            model_name='line',
            name='fare_dza',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text='Fare in Algerian Dinars',
                verbose_name='fare (DZA)',
            ),
        ),
    ]
