from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stations', '0002_chargingsite_chargingstation_site'),
    ]

    operations = [
        migrations.CreateModel(
            name='FaultLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reported_at', models.DateTimeField(verbose_name='장애 발생 시각')),
                ('fault_type', models.CharField(
                    choices=[
                        ('connector', '커넥터 불량'),
                        ('comm', '통신 오류'),
                        ('power', '전원 불량'),
                        ('display', '디스플레이 불량'),
                        ('other', '기타'),
                    ],
                    default='other',
                    max_length=20,
                )),
                ('description', models.TextField(verbose_name='장애 내용')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='복구 시각')),
                ('reported_by', models.CharField(max_length=50, verbose_name='입력자')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('charging_station', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fault_logs',
                    to='stations.chargingstation',
                    verbose_name='충전기',
                )),
            ],
            options={
                'verbose_name': 'Fault Log',
                'verbose_name_plural': 'Fault Logs',
                'db_table': 'cp_fault_log',
                'ordering': ['-reported_at'],
            },
        ),
    ]
