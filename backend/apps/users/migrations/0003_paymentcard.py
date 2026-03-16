from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_role_status_partnerprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nickname', models.CharField(max_length=50, verbose_name='카드 별칭')),
                ('card_last4', models.CharField(max_length=4, verbose_name='카드 끝 4자리')),
                ('card_type', models.CharField(
                    choices=[('Visa', 'Visa'), ('Mastercard', 'Mastercard'), ('국내카드', '국내카드'), ('기타', '기타')],
                    default='국내카드',
                    max_length=20,
                )),
                ('billing_key', models.CharField(blank=True, max_length=200, verbose_name='PG 빌링키')),
                ('is_default', models.BooleanField(default=False, verbose_name='기본 결제 카드')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payment_cards',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Payment Card',
                'verbose_name_plural': 'Payment Cards',
                'db_table': 'cp_payment_card',
            },
        ),
    ]
