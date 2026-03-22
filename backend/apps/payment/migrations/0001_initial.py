import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('mobile_api', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_reference', models.CharField(max_length=80, unique=True)),
                ('station_id', models.CharField(max_length=64)),
                ('prepaid_amount', models.DecimalField(decimal_places=0, max_digits=12)),
                ('actual_amount', models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True)),
                ('refund_amount', models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', '결제 대기'),
                        ('PAID', 'IPN 수신 완료'),
                        ('CHARGING', '충전 중'),
                        ('COMPLETED', '충전 완료'),
                        ('REFUNDED', '차액 환불 완료'),
                        ('FAILED', '결제 실패'),
                        ('CANCELED', '사용자 취소'),
                    ],
                    default='PENDING',
                    max_length=10,
                )),
                ('mb_transaction_id', models.CharField(blank=True, max_length=100)),
                ('trans_date', models.CharField(blank=True, max_length=10)),
                ('payment_url', models.URLField(blank=True, max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('app_session', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_transaction',
                    to='mobile_api.appsession',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='payment_transactions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Payment Transaction',
                'verbose_name_plural': 'Payment Transactions',
                'db_table': 'cp_payment_transaction',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='paymenttransaction',
            index=models.Index(fields=['user', 'created_at'], name='cp_payment_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='paymenttransaction',
            index=models.Index(fields=['status', 'created_at'], name='cp_payment_status_created_idx'),
        ),
    ]
