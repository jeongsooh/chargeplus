"""
Payment API 엔드포인트.

POST   /api/payment/create/        결제 세션 생성 (JWT 인증)
POST   /api/payment/ipn/           MB IPN 웹훅 (인증 없음, CSRF 제외)
GET    /api/payment/status/<ref>/  결제 상태 조회 (JWT 인증)
GET    /api/payment/return/        결제 완료 리턴 URL
GET    /api/payment/cancel/        결제 취소 리턴 URL
GET    /api/payment/mock/          Mock MB Paygate UI (sandbox only)
POST   /api/payment/mock/submit/   Mock 결제 제출 (sandbox only)
"""
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status as http_status

from apps.payment.models import PaymentTransaction
from apps.payment.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


class PaymentCreateView(APIView):
    """
    POST /api/payment/create/
    결제 세션 생성 → MB create-order → payment_url 반환.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.stations.models import ChargingStation
        from apps.ocpp16.services.gateway_client import GatewayClient

        station_id = request.data.get('station_id', '').strip()
        if not station_id:
            return Response({'error': 'station_id가 필요합니다.'}, status=http_status.HTTP_400_BAD_REQUEST)

        amount = request.data.get('amount')
        if amount is None:
            amount = int(getattr(settings, 'MB_PREPAID_AMOUNT', 100000))
        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response({'error': 'amount는 양의 정수여야 합니다.'}, status=http_status.HTTP_400_BAD_REQUEST)

        # station 존재 여부 확인
        try:
            ChargingStation.objects.get(station_id=station_id, is_active=True)
        except ChargingStation.DoesNotExist:
            return Response({'error': '존재하지 않는 충전기입니다.'}, status=http_status.HTTP_404_NOT_FOUND)

        # 충전기 온라인 확인
        if not GatewayClient.is_station_connected(station_id):
            return Response({'error': '충전기가 오프라인입니다.'}, status=http_status.HTTP_503_SERVICE_UNAVAILABLE)

        # 진행 중인 결제 세션 중복 확인
        existing = PaymentTransaction.objects.filter(
            user=request.user,
            status__in=[
                PaymentTransaction.Status.PENDING,
                PaymentTransaction.Status.PAID,
                PaymentTransaction.Status.CHARGING,
            ],
        ).exists()
        if existing:
            return Response(
                {'error': '이미 진행 중인 결제 세션이 있습니다.'},
                status=http_status.HTTP_409_CONFLICT,
            )

        ip_address = _get_client_ip(request)
        pt = PaymentService.create_payment(
            user=request.user,
            station_id=station_id,
            amount=amount,
            ip_address=ip_address,
        )

        is_mock = pt.payment_url.startswith('/api/payment/mock/')
        return Response({
            'order_reference': pt.order_reference,
            'payment_url': pt.payment_url,
            'is_mock': is_mock,
        }, status=http_status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class PaymentIpnView(APIView):
    """
    POST /api/payment/ipn/
    MB Paygate IPN 웹훅. MAC 검증 후 결제 완료 처리.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = request.data if hasattr(request, 'data') else {}
        if not data:
            import json as _json
            try:
                data = _json.loads(request.body)
            except Exception:
                data = {}

        logger.info(f"IPN received: {data}")

        success = PaymentService.handle_ipn(data)

        if success:
            return JsonResponse({'errorCode': '00'})
        else:
            return JsonResponse({'errorCode': '99'})


class PaymentStatusView(APIView):
    """
    GET /api/payment/status/<order_reference>/
    결제 상태 조회. PENDING이면 MB inquiry API 재조회.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_reference):
        try:
            pt = PaymentTransaction.objects.get(order_reference=order_reference)
        except PaymentTransaction.DoesNotExist:
            return Response(status=http_status.HTTP_404_NOT_FOUND)

        if pt.user != request.user:
            return Response(status=http_status.HTTP_403_FORBIDDEN)

        # PENDING이면 MB 재조회
        if pt.status == PaymentTransaction.Status.PENDING:
            current_status = PaymentService.query_status(order_reference)
        else:
            current_status = pt.status

        return Response({
            'order_reference': order_reference,
            'status': current_status,
            'session_id': pt.app_session.session_id if pt.app_session_id else None,
        })


class PaymentReturnView(APIView):
    """GET /api/payment/return/ — 결제 완료 후 MB가 리다이렉트하는 URL."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        order_reference = request.query_params.get('order_reference', '')
        logger.info(f"Payment return: order={order_reference} params={dict(request.query_params)}")
        return HttpResponse(
            '<html><body><h2>결제가 완료되었습니다. 앱으로 돌아가 충전을 시작하세요.</h2></body></html>',
            content_type='text/html; charset=utf-8',
        )


class PaymentCancelView(APIView):
    """GET /api/payment/cancel/ — 결제 취소 후 MB가 리다이렉트하는 URL."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        order_reference = request.query_params.get('order_reference', '')
        logger.info(f"Payment cancel: order={order_reference}")

        if order_reference:
            PaymentTransaction.objects.filter(
                order_reference=order_reference,
                status=PaymentTransaction.Status.PENDING,
            ).update(status=PaymentTransaction.Status.CANCELED)

        return HttpResponse(
            '<html><body><h2>결제가 취소되었습니다.</h2></body></html>',
            content_type='text/html; charset=utf-8',
        )


class PaymentMockView(APIView):
    """
    GET  /api/payment/mock/          Mock MB Paygate UI
    POST /api/payment/mock/submit/   Mock 결제 제출
    Sandbox 전용.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        if not getattr(settings, 'MB_SANDBOX', True):
            return Response({'error': 'Mock UI는 sandbox에서만 사용 가능합니다.'}, status=http_status.HTTP_404_NOT_FOUND)

        order_reference = request.query_params.get('order', '')
        try:
            pt = PaymentTransaction.objects.get(order_reference=order_reference)
        except PaymentTransaction.DoesNotExist:
            return HttpResponse('<html><body><h2>Invalid order reference.</h2></body></html>', content_type='text/html; charset=utf-8')

        html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Mock MB Paygate</title>
<style>body{{font-family:sans-serif;max-width:400px;margin:60px auto;padding:20px}}
.btn{{background:#0066cc;color:#fff;border:none;padding:12px 24px;font-size:16px;cursor:pointer;border-radius:4px}}
.btn-cancel{{background:#ccc;color:#333;margin-left:8px}}</style>
</head>
<body>
<h2>MB Paygate (Mock)</h2>
<p><strong>주문번호:</strong> {pt.order_reference}</p>
<p><strong>결제금액:</strong> {int(pt.prepaid_amount):,} VND</p>
<p><strong>충전기:</strong> {pt.station_id}</p>
<form method="POST" action="/api/payment/mock/submit/">
  <input type="hidden" name="order_reference" value="{pt.order_reference}">
  <input type="hidden" name="csrfmiddlewaretoken" value="mock-csrf">
  <button type="submit" class="btn">결제하기</button>
  <a href="/api/payment/cancel/?order_reference={pt.order_reference}">
    <button type="button" class="btn btn-cancel">취소</button>
  </a>
</form>
</body>
</html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8')


@method_decorator(csrf_exempt, name='dispatch')
class PaymentMockSubmitView(APIView):
    """
    POST /api/payment/mock/submit/
    Mock 결제 제출 → IPN 내부 발송 → CHARGING 상태로 전환.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if not getattr(settings, 'MB_SANDBOX', True):
            return Response({'error': 'Mock은 sandbox에서만 사용 가능합니다.'}, status=http_status.HTTP_404_NOT_FOUND)

        order_reference = request.data.get('order_reference', '') or request.POST.get('order_reference', '')
        if not order_reference:
            return Response({'error': 'order_reference가 필요합니다.'}, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            pt = PaymentTransaction.objects.get(order_reference=order_reference)
        except PaymentTransaction.DoesNotExist:
            return Response({'error': '주문을 찾을 수 없습니다.'}, status=http_status.HTTP_404_NOT_FOUND)

        if pt.status != PaymentTransaction.Status.PENDING:
            return HttpResponse(
                f'<html><body><h2>이미 처리된 주문입니다. 상태: {pt.status}</h2></body></html>',
                content_type='text/html; charset=utf-8',
            )

        # Mock IPN 데이터 생성 (MAC 검증 우회)
        import hashlib, time as _time
        fake_txn_id = f"MOCK{int(_time.time()*1000)}"

        # MAC 재계산 (실제 MB가 보내는 것처럼)
        from django.conf import settings as _settings
        from apps.payment.services.mac import generate_mac

        ipn_data = {
            'error_code': '00',
            'merchant_id': _settings.MB_MERCHANT_ID,
            'order_reference': order_reference,
            'pg_transaction_number': fake_txn_id,
            'amount': str(int(pt.prepaid_amount)),
            'currency': 'VND',
        }
        ipn_data['mac'] = generate_mac(ipn_data, _settings.MB_SECRET_KEY)
        ipn_data['mac_type'] = 'MD5'

        success = PaymentService.handle_ipn(ipn_data)

        if success:
            return HttpResponse(
                f'<html><body><h2>결제 성공!</h2><p>충전이 곧 시작됩니다. 앱에서 상태를 확인하세요.</p>'
                f'<p>주문번호: {order_reference}</p></body></html>',
                content_type='text/html; charset=utf-8',
            )
        else:
            return HttpResponse(
                '<html><body><h2>결제 처리 실패. 다시 시도해주세요.</h2></body></html>',
                content_type='text/html; charset=utf-8',
            )
