"""
결제 E2E 통합 테스트.

Mock MB 서버를 활용한 전체 플로우 검증:
1. POST /api/payment/create/ → Mock URL 수신
2. GET /api/payment/mock/?order=<ref>  → Mock 결제 페이지
3. POST /api/payment/mock/submit/ → IPN 내부 발송
4. GET /api/payment/status/<ref>/ 폴링 → CHARGING 확인
5. CP 시뮬레이터 MeterValues (AppSession kwh_current 갱신 확인)
6. POST /api/charge/stop → StopTransaction 처리
7. GET /api/payment/status/<ref>/ → REFUNDED or COMPLETED 확인

실행 방법:
    docker compose exec backend python manage.py test apps.payment.tests tests.test_payment_flow
"""
import json
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

MB_SETTINGS = {
    'MB_SECRET_KEY': '6ca6af4578753e1afae2eb864f8aa288',
    'MB_ACCESS_CODE': 'DNHXPHRNMZ',
    'MB_MERCHANT_ID': '114743',
    'MB_SANDBOX': True,
    'MB_RETURN_URL': 'http://testserver/api/payment/return/',
    'MB_CANCEL_URL': 'http://testserver/api/payment/cancel/',
    'MB_PREPAID_AMOUNT': 100000,
}


@override_settings(**MB_SETTINGS)
class PaymentCreateTest(TestCase):
    """POST /api/payment/create/ 엔드포인트 테스트."""

    def setUp(self):
        from apps.users.models import User
        from apps.stations.models import ChargingStation

        self.user = User.objects.create_user(
            username='testpay', password='testpass1234', phone='0901234567'
        )
        self.station = ChargingStation.objects.create(
            station_id='CP001', name='Test Station', is_active=True
        )
        self.client = APIClient()
        token = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_create_payment_station_offline(self):
        """오프라인 충전기에 결제 요청 → 503."""
        with patch('apps.ocpp16.services.gateway_client.GatewayClient.is_station_connected', return_value=False):
            resp = self.client.post('/api/payment/create/', {'station_id': 'CP001', 'amount': 100000})
        self.assertEqual(resp.status_code, 503)

    def test_create_payment_station_not_found(self):
        """존재하지 않는 충전기 → 404."""
        with patch('apps.ocpp16.services.gateway_client.GatewayClient.is_station_connected', return_value=True):
            resp = self.client.post('/api/payment/create/', {'station_id': 'NOTEXIST', 'amount': 100000})
        self.assertEqual(resp.status_code, 404)

    def test_create_payment_mb_failure_returns_mock_url(self):
        """MB 연결 실패 시 Mock URL 반환."""
        from apps.payment.services import mb_client
        with patch('apps.ocpp16.services.gateway_client.GatewayClient.is_station_connected', return_value=True), \
             patch.object(mb_client.MBPaygateClient, 'create_order', return_value={'error_code': 'CONN_ERR', 'trans_date': '22032026'}):
            resp = self.client.post('/api/payment/create/', {'station_id': 'CP001', 'amount': 100000})
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['is_mock'])
        self.assertIn('/api/payment/mock/', data['payment_url'])
        self.assertIn('order_reference', data)

    def test_duplicate_payment_returns_409(self):
        """진행 중인 결제 세션이 있으면 409."""
        from apps.payment.models import PaymentTransaction
        PaymentTransaction.objects.create(
            order_reference='CP_EXISTING',
            user=self.user,
            station_id='CP001',
            prepaid_amount=100000,
            status=PaymentTransaction.Status.PENDING,
        )
        with patch('apps.ocpp16.services.gateway_client.GatewayClient.is_station_connected', return_value=True):
            resp = self.client.post('/api/payment/create/', {'station_id': 'CP001', 'amount': 100000})
        self.assertEqual(resp.status_code, 409)


@override_settings(**MB_SETTINGS)
class PaymentIpnTest(TestCase):
    """IPN 처리 테스트."""

    def setUp(self):
        from apps.users.models import User
        from apps.payment.models import PaymentTransaction

        self.user = User.objects.create_user(username='testipn', password='testpass1234')
        self.pt = PaymentTransaction.objects.create(
            order_reference='CP_IPN_TEST_001',
            user=self.user,
            station_id='CP001',
            prepaid_amount=100000,
            status=PaymentTransaction.Status.PENDING,
            trans_date='22032026',
        )
        self.client = APIClient()

    def _make_ipn_payload(self, order_reference: str, error_code: str = '00') -> dict:
        from apps.payment.services.mac import generate_mac
        data = {
            'error_code': error_code,
            'merchant_id': '114743',
            'order_reference': order_reference,
            'pg_transaction_number': 'MBTEST_TXN_123',
            'amount': '100000',
            'currency': 'VND',
        }
        data['mac'] = generate_mac(data, '6ca6af4578753e1afae2eb864f8aa288')
        data['mac_type'] = 'MD5'
        return data

    def test_ipn_mac_invalid_returns_error(self):
        """MAC 불일치 IPN → errorCode 99."""
        payload = self._make_ipn_payload('CP_IPN_TEST_001')
        payload['mac'] = 'INVALIDMAC12345678901234567890AB'
        resp = self.client.post('/api/payment/ipn/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['errorCode'], '99')

    def test_ipn_success_triggers_celery(self):
        """유효한 IPN → PAID 저장 + Celery task 트리거."""
        payload = self._make_ipn_payload('CP_IPN_TEST_001')
        with patch('apps.payment.tasks.trigger_remote_start.apply_async') as mock_task:
            resp = self.client.post('/api/payment/ipn/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['errorCode'], '00')

        from apps.payment.models import PaymentTransaction
        self.pt.refresh_from_db()
        self.assertEqual(self.pt.status, PaymentTransaction.Status.PAID)
        self.assertEqual(self.pt.mb_transaction_id, 'MBTEST_TXN_123')
        mock_task.assert_called_once()

    def test_ipn_idempotent(self):
        """중복 IPN → 두 번째는 스킵 (멱등성)."""
        payload = self._make_ipn_payload('CP_IPN_TEST_001')
        with patch('apps.payment.tasks.trigger_remote_start.apply_async') as mock_task:
            self.client.post('/api/payment/ipn/', payload, format='json')
            self.client.post('/api/payment/ipn/', payload, format='json')  # 두 번째
        # Celery는 한 번만 호출
        self.assertEqual(mock_task.call_count, 1)

    def test_ipn_error_code_marks_failed(self):
        """MB error_code 비정상 → FAILED."""
        payload = self._make_ipn_payload('CP_IPN_TEST_001', error_code='99')
        resp = self.client.post('/api/payment/ipn/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['errorCode'], '99')

        self.pt.refresh_from_db()
        from apps.payment.models import PaymentTransaction
        self.assertEqual(self.pt.status, PaymentTransaction.Status.FAILED)


@override_settings(**MB_SETTINGS)
class MockPaymentFlowTest(TestCase):
    """Mock MB Paygate를 활용한 결제 플로우 테스트."""

    def setUp(self):
        from apps.users.models import User
        from apps.stations.models import ChargingStation
        from apps.payment.models import PaymentTransaction

        self.user = User.objects.create_user(username='flowtest', password='testpass1234')
        self.station = ChargingStation.objects.create(
            station_id='CP_FLOW', name='Flow Station', is_active=True
        )
        self.pt = PaymentTransaction.objects.create(
            order_reference='CP_FLOW_001',
            user=self.user,
            station_id='CP_FLOW',
            prepaid_amount=100000,
            status=PaymentTransaction.Status.PENDING,
            payment_url='/api/payment/mock/?order=CP_FLOW_001',
            trans_date='22032026',
        )
        self.client = APIClient()
        token = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_mock_ui_page_renders(self):
        """Mock 결제 페이지 렌더링 확인."""
        resp = self.client.get('/api/payment/mock/?order=CP_FLOW_001')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'CP_FLOW_001', resp.content)
        self.assertIn(b'100,000', resp.content)

    def test_mock_submit_triggers_ipn_and_celery(self):
        """Mock 제출 → IPN 처리 → PAID + Celery task 호출."""
        with patch('apps.payment.tasks.trigger_remote_start.apply_async') as mock_task:
            resp = self.client.post('/api/payment/mock/submit/', {'order_reference': 'CP_FLOW_001'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'결제 성공', resp.content)
        mock_task.assert_called_once_with(args=['CP_FLOW_001'], queue='ocpp.q.commands')

        self.pt.refresh_from_db()
        from apps.payment.models import PaymentTransaction
        self.assertEqual(self.pt.status, PaymentTransaction.Status.PAID)

    def test_payment_status_endpoint(self):
        """GET /api/payment/status/<ref>/ 조회 테스트."""
        resp = self.client.get(f'/api/payment/status/CP_FLOW_001/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'PENDING')
        self.assertEqual(data['order_reference'], 'CP_FLOW_001')

    def test_payment_status_wrong_user_returns_403(self):
        """다른 사용자의 결제 상태 조회 → 403."""
        from apps.users.models import User
        other = User.objects.create_user(username='other', password='testpass1234')
        other_token = RefreshToken.for_user(other)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token.access_token}')
        resp = other_client.get(f'/api/payment/status/CP_FLOW_001/')
        self.assertEqual(resp.status_code, 403)
