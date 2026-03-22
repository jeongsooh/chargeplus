from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stations', '0003_faultlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='chargingstation',
            name='num_evses',
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name='EVSE 수',
                help_text='충전기 내 EVSE(충전 유닛) 개수',
            ),
        ),
        migrations.AddField(
            model_name='chargingstation',
            name='num_connectors_per_evse',
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name='EVSE당 커넥터 수',
                help_text='각 EVSE에 포함된 커넥터 개수. 총 커넥터 = EVSE 수 × 커넥터 수',
            ),
        ),
    ]
