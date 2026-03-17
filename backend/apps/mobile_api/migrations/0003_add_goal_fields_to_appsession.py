from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_api', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsession',
            name='goal_type',
            field=models.CharField(
                choices=[
                    ('time', 'Time (minutes)'),
                    ('kwh', 'Energy (kWh)'),
                    ('amount', 'Amount (KRW)'),
                    ('free', 'Free (no limit)'),
                ],
                default='free',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='appsession',
            name='goal_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
