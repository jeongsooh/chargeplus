"""결제 비즈니스 로직."""
import logging
import random
import time
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.payment.models import PaymentTransaction
from .mac import generate_mac
from .mb_client import MBPaygateClient

logger = logging.getLogger(__name__)


def _make_order_reference() -> str:
    """CP prefix + timestamp + random suffix. 최대 80자."""
    ts = int(time.time() * 1000)
    rnd = random.randint(1000, 9999)
    return f"CP{ts}{rnd}"


class PaymentService:

    @classmethod
    def create_payment(cls, user, station_id: str, amount: int, ip_address: str) -> PaymentTransaction:
        """
        PaymentTransaction 생성 + MB create-order 호출.
        MB 연결 실패 시 payment_url은 Mock URL로 설정.
        """
        order_reference = _make_order_reference()
        prepaid_amount = Decimal(str(amount))

        # customer 정보
        customer_id = user.phone or user.username
        customer_name = user.get_full_name() or user.username

        pt = PaymentTransaction.objects.create(
            order_reference=order_reference,
            user=user,
            station_id=station_id,
            prepaid_amount=prepaid_amount,
            status=PaymentTransaction.Status.PENDING,
        )

        client = MBPaygateClient()
        return_url = getattr(settings, 'MB_RETURN_URL', '')
        cancel_url = getattr(settings, 'MB_CANCEL_URL', '')

        result = client.create_order(
            order_reference=order_reference,
            amount=amount,
            station_id=station_id,
            customer_id=customer_id,
            customer_name=customer_name,
            ip_address=ip_address,
            return_url=return_url,
            cancel_url=cancel_url,
        )

        error_code = result.get('error_code', '')
        qr_url = result.get('qr_url', '')
        payment_url = result.get('payment_url', '') or qr_url
        trans_date = result.get('trans_date', timezone.now().strftime('%d%m%Y'))

        pt.trans_date = trans_date
        if error_code == '00' and payment_url:
            pt.payment_url = payment_url
        else:
            # sandbox 연결 실패 또는 오류 → Mock URL 반환
            pt.payment_url = f'/api/payment/mock/?order={order_reference}'

        pt.save(update_fields=['payment_url', 'trans_date', 'updated_at'])
        return pt

    @classmethod
    def handle_ipn(cls, data: dict) -> bool:
        """
        IPN 처리: MAC 검증 → PAID 저장 → Celery task 트리거.

        Returns:
            True if processed successfully, False if invalid/already processed.
        """
        received_mac = data.get('mac', '')
        error_code = data.get('error_code', '')

        # MAC 재계산 검증
        mac_data = {k: v for k, v in data.items() if k not in ('mac', 'mac_type')}
        expected_mac = generate_mac(mac_data, settings.MB_SECRET_KEY)

        if received_mac.upper() != expected_mac.upper():
            logger.warning(
                f"IPN MAC mismatch: received={received_mac} expected={expected_mac} "
                f"order={data.get('order_reference', '')}"
            )
            return False

        if error_code != '00':
            logger.info(f"IPN error_code={error_code} for order={data.get('order_reference', '')}")
            order_ref = data.get('order_reference', '')
            if order_ref:
                PaymentTransaction.objects.filter(
                    order_reference=order_ref,
                    status=PaymentTransaction.Status.PENDING,
                ).update(status=PaymentTransaction.Status.FAILED, updated_at=timezone.now())
            return False

        order_reference = data.get('order_reference', '')
        mb_transaction_id = data.get('pg_transaction_number', '')

        # 멱등성: PENDING 상태인 경우만 처리
        updated = PaymentTransaction.objects.filter(
            order_reference=order_reference,
            status=PaymentTransaction.Status.PENDING,
        ).update(
            status=PaymentTransaction.Status.PAID,
            mb_transaction_id=mb_transaction_id,
            updated_at=timezone.now(),
        )

        if not updated:
            logger.info(f"IPN skipped (not PENDING): order={order_reference}")
            return True  # 멱등성 처리 — 성공으로 응답

        logger.info(f"IPN processed: order={order_reference} mb_txn={mb_transaction_id}")

        # Celery task 비동기 실행
        from apps.payment.tasks import trigger_remote_start
        trigger_remote_start.apply_async(args=[order_reference], queue='ocpp.q.commands')

        return True

    @classmethod
    def process_stop(cls, app_session) -> None:
        """
        충전 종료 후 actual_amount 계산 → MB refund 호출.
        AppSession이 payment_transaction과 연결되어 있지 않으면 스킵.
        """
        try:
            pt = app_session.payment_transaction
        except PaymentTransaction.DoesNotExist:
            return
        except Exception:
            return

        if pt.status != PaymentTransaction.Status.CHARGING:
            return

        from apps.ocpp16.services.pricing import PricingService
        actual_kwh = float(app_session.final_kwh or 0)
        station_id = app_session.charging_station.station_id
        actual_cost = PricingService.calculate(station_id, actual_kwh)

        actual_amount = Decimal(str(actual_cost))
        refund_amount = pt.prepaid_amount - actual_amount

        new_status = PaymentTransaction.Status.COMPLETED

        if refund_amount > 0 and pt.mb_transaction_id and pt.trans_date:
            client = MBPaygateClient()
            result = client.refund(
                txn_amount=int(refund_amount),
                transaction_reference_id=pt.mb_transaction_id,
                trans_date=pt.trans_date,
            )
            if result.get('error_code') == '00':
                new_status = PaymentTransaction.Status.REFUNDED
                logger.info(
                    f"MB refund success: order={pt.order_reference} "
                    f"refund={refund_amount}VND"
                )
            else:
                logger.error(
                    f"MB refund failed: order={pt.order_reference} "
                    f"error_code={result.get('error_code')}"
                )

        pt.actual_amount = actual_amount
        pt.refund_amount = max(Decimal('0'), refund_amount)
        pt.status = new_status
        pt.save(update_fields=['actual_amount', 'refund_amount', 'status', 'updated_at'])

        logger.info(
            f"process_stop: order={pt.order_reference} "
            f"prepaid={pt.prepaid_amount} actual={actual_amount} "
            f"refund={pt.refund_amount} status={new_status}"
        )

    @classmethod
    def query_status(cls, order_reference: str) -> str:
        """
        PENDING 상태 시 MB inquiry API 재조회하여 실제 결제 여부 확인.
        DB status를 보정하고 최신 status를 반환.
        """
        try:
            pt = PaymentTransaction.objects.get(order_reference=order_reference)
        except PaymentTransaction.DoesNotExist:
            return 'NOT_FOUND'

        if pt.status != PaymentTransaction.Status.PENDING:
            return pt.status

        client = MBPaygateClient()
        result = client.inquiry(order_reference=order_reference, pay_date=pt.trans_date)

        if result.get('error_code') == '00':
            # 실제 결제 완료 — IPN을 받지 못한 경우
            mb_txn = result.get('pg_transaction_number', '')
            PaymentTransaction.objects.filter(
                order_reference=order_reference,
                status=PaymentTransaction.Status.PENDING,
            ).update(
                status=PaymentTransaction.Status.PAID,
                mb_transaction_id=mb_txn,
                updated_at=timezone.now(),
            )
            # Celery task 트리거
            from apps.payment.tasks import trigger_remote_start
            trigger_remote_start.apply_async(args=[order_reference], queue='ocpp.q.commands')
            return PaymentTransaction.Status.PAID

        return pt.status
