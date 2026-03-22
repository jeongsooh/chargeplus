"""
Payment Celery tasks.
trigger_remote_start: IPN → RemoteStartTransaction → AppSession 연결
"""
import logging
import time

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    queue='ocpp.q.commands',
    bind=True,
    max_retries=2,
    name='apps.payment.tasks.trigger_remote_start',
)
def trigger_remote_start(self, order_reference: str):
    """
    IPN 수신 후 호출. AppSession 생성 + RemoteStartTransaction 전송.

    성공: PaymentTransaction.status = CHARGING, app_session 연결
    실패: PaymentTransaction.status = FAILED
    """
    from apps.payment.models import PaymentTransaction
    from apps.mobile_api.models import AppSession
    from apps.stations.models import ChargingStation, Connector
    from apps.ocpp16.services.gateway_client import GatewayClient
    from apps.ocpp16.tasks.core import check_pending_session_timeout
    from apps.config.models import CsmsVariable

    try:
        pt = PaymentTransaction.objects.get(order_reference=order_reference)
    except PaymentTransaction.DoesNotExist:
        logger.error(f"trigger_remote_start: PaymentTransaction {order_reference} not found")
        return

    if pt.status != PaymentTransaction.Status.PAID:
        logger.warning(
            f"trigger_remote_start: {order_reference} status is {pt.status}, skipping"
        )
        return

    station_id = pt.station_id

    # 충전기 연결 확인
    if not GatewayClient.is_station_connected(station_id):
        pt.status = PaymentTransaction.Status.FAILED
        pt.save(update_fields=['status', 'updated_at'])
        logger.error(f"trigger_remote_start: station {station_id} not connected")
        return

    # station 조회
    try:
        station = ChargingStation.objects.get(station_id=station_id)
    except ChargingStation.DoesNotExist:
        pt.status = PaymentTransaction.Status.FAILED
        pt.save(update_fields=['status', 'updated_at'])
        logger.error(f"trigger_remote_start: station {station_id} not in DB")
        return

    # 사용 가능한 커넥터 확인
    connector = Connector.objects.filter(
        evse__charging_station=station,
        current_status=Connector.Status.AVAILABLE,
    ).first()
    connector_id = connector.connector_id if connector else 1

    # AppSession 생성
    session_id = f"pay_{int(time.time())}_{station_id}"
    app_session = AppSession.objects.create(
        session_id=session_id,
        user=pt.user,
        charging_station=station,
        connector_id=connector_id,
        status=AppSession.Status.PENDING,
        goal_type=AppSession.GoalType.FREE,
    )

    # RemoteStartTransaction 전송
    id_tag = f"APP-{pt.user.pk}"
    try:
        result = GatewayClient.send_command(
            station_id,
            'RemoteStartTransaction',
            {'idTag': id_tag, 'connectorId': connector_id},
            timeout=10,
        )
        if result.get('status') == 'Rejected':
            raise Exception("RemoteStartTransaction Rejected by charge point")
    except Exception as exc:
        logger.error(f"trigger_remote_start RemoteStart failed for {order_reference}: {exc}")
        pt.status = PaymentTransaction.Status.FAILED
        pt.save(update_fields=['status', 'updated_at'])
        app_session.status = AppSession.Status.FAILED
        app_session.fail_reason = f'충전기 원격 시작 실패: {exc}'
        app_session.save(update_fields=['status', 'fail_reason', 'updated_at'])
        return

    # 성공: PaymentTransaction에 AppSession 연결 + CHARGING 상태
    pt.app_session = app_session
    pt.status = PaymentTransaction.Status.CHARGING
    pt.save(update_fields=['app_session', 'status', 'updated_at'])

    # pending 세션 타임아웃 체크 예약
    timeout_seconds = int(CsmsVariable.get('pending_session_timeout', default=120))
    check_pending_session_timeout.apply_async(
        args=[session_id],
        countdown=timeout_seconds,
    )

    logger.info(
        f"trigger_remote_start success: order={order_reference} "
        f"session={session_id} station={station_id}"
    )
