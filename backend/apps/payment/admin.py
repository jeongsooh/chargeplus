import logging

from django.contrib import admin
from django.utils import timezone

from .models import PaymentTransaction
from .services.mb_client import MBPaygateClient
from .services.payment_service import PaymentService

logger = logging.getLogger(__name__)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'order_reference', 'user', 'station_id',
        'prepaid_amount', 'actual_amount', 'refund_amount',
        'status', 'mb_transaction_id', 'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['order_reference', 'mb_transaction_id', 'user__username', 'station_id']
    readonly_fields = [
        'order_reference', 'mb_transaction_id', 'trans_date',
        'created_at', 'updated_at',
    ]
    date_hierarchy = 'created_at'
    actions = ['action_manual_refund', 'action_requery_status']

    def action_manual_refund(self, request, queryset):
        """선택된 CHARGING 상태 거래에 대해 수동 환불 처리."""
        count = 0
        for pt in queryset.filter(status=PaymentTransaction.Status.CHARGING):
            if pt.app_session:
                try:
                    PaymentService.process_stop(pt.app_session)
                    count += 1
                except Exception as e:
                    logger.error(f"Manual refund failed for {pt.order_reference}: {e}")
        self.message_user(request, f"{count}건 환불 처리 완료.")

    action_manual_refund.short_description = '선택 건 수동 환불 처리'

    def action_requery_status(self, request, queryset):
        """MB inquiry API로 상태 재조회."""
        results = []
        for pt in queryset.filter(status=PaymentTransaction.Status.PENDING):
            new_status = PaymentService.query_status(pt.order_reference)
            results.append(f"{pt.order_reference}: {new_status}")
        self.message_user(request, "재조회 결과: " + ", ".join(results) if results else "PENDING 거래 없음.")

    action_requery_status.short_description = 'MB 상태 재조회'
