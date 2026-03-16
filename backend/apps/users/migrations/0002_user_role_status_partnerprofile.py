from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('cs', '고객센터'), ('partner', '파트너'), ('customer', '고객')],
                default='customer',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[('pending', '승인대기'), ('active', '활성'), ('inactive', '비활성')],
                default='active',
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name='PartnerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(max_length=100, verbose_name='사업체명')),
                ('business_no', models.CharField(max_length=20, verbose_name='사업자번호')),
                ('contact_phone', models.CharField(blank=True, max_length=20, verbose_name='담당자 연락처')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(
                    limit_choices_to={'role': 'partner'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='partner_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Partner Profile',
                'verbose_name_plural': 'Partner Profiles',
                'db_table': 'cp_partner_profile',
            },
        ),
    ]
