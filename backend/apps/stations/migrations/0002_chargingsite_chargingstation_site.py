from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stations', '0001_initial'),
        ('users', '0002_user_role_status_partnerprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChargingSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(max_length=100, verbose_name='충전소명')),
                ('address', models.CharField(blank=True, max_length=200, verbose_name='주소')),
                ('unit_price', models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name='충전단가(원/kWh)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('partner', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sites',
                    to='users.partnerprofile',
                    verbose_name='파트너',
                )),
            ],
            options={
                'verbose_name': 'Charging Site',
                'verbose_name_plural': 'Charging Sites',
                'db_table': 'cp_charging_site',
            },
        ),
        migrations.AddField(
            model_name='chargingstation',
            name='site',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stations',
                to='stations.chargingsite',
                verbose_name='충전소',
            ),
        ),
    ]
