from django.db import models


class PaymentTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING   = 'PENDING',   '결제 대기'
        PAID      = 'PAID',      'IPN 수신 완료'
        CHARGING  = 'CHARGING',  '충전 중'
        COMPLETED = 'COMPLETED', '충전 완료'
        REFUNDED  = 'REFUNDED',  '차액 환불 완료'
        FAILED    = 'FAILED',    '결제 실패'
        CANCELED  = 'CANCELED',  '사용자 취소'

    order_reference  = models.CharField(max_length=80, unique=True)
    app_session      = models.OneToOneField(
        'mobile_api.AppSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transaction',
    )
    user             = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='payment_transactions',
    )
    station_id       = models.CharField(max_length=64)
    prepaid_amount   = models.DecimalField(max_digits=12, decimal_places=0)
    actual_amount    = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    refund_amount    = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    status           = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    mb_transaction_id = models.CharField(max_length=100, blank=True)
    trans_date       = models.CharField(max_length=10, blank=True)   # ddMMyyyy
    payment_url      = models.URLField(max_length=512, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_payment_transaction'
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_reference} ({self.status}) user={self.user_id}"
