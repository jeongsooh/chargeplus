import logging

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChargingStation
from .serializers import ChargingStationSerializer, ChargingStationListSerializer

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS = [
    'Reset',
    'ChangeAvailability',
    'ChangeConfiguration',
    'GetConfiguration',
    'ClearCache',
    'RemoteStartTransaction',
    'RemoteStopTransaction',
    'UnlockConnector',
    'TriggerMessage',
    'UpdateFirmware',
    'GetDiagnostics',
    'GetLocalListVersion',
    'SendLocalList',
    'ReserveNow',
    'CancelReservation',
    'SetChargingProfile',
    'ClearChargingProfile',
    'GetCompositeSchedule',
    'DataTransfer',
]


class ChargingStationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving charging stations.
    """
    queryset = ChargingStation.objects.select_related('operator').prefetch_related(
        'evses__connectors'
    ).order_by('station_id')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return ChargingStationListSerializer
        return ChargingStationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        operator = self.request.query_params.get('operator')
        if operator:
            qs = qs.filter(operator__code=operator)
        active_only = self.request.query_params.get('active', 'true').lower()
        if active_only == 'true':
            qs = qs.filter(is_active=True)
        return qs


class CommandView(APIView):
    """
    Send CSMS → CP OCPP commands.
    POST /api/v1/stations/{station_id}/command/
    Body: {"action": "Reset", "payload": {"type": "Soft"}}
    """
    permission_classes = [IsAdminUser]

    def post(self, request, station_id):
        from apps.ocpp16.services.gateway_client import GatewayClient

        action = request.data.get('action')
        payload = request.data.get('payload', {})

        if not action:
            return Response({'error': 'action is required'}, status=status.HTTP_400_BAD_REQUEST)

        if action not in ALLOWED_COMMANDS:
            return Response(
                {'error': f'Unknown action: {action}. Allowed: {ALLOWED_COMMANDS}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate station exists
        try:
            station = ChargingStation.objects.get(station_id=station_id)
        except ChargingStation.DoesNotExist:
            return Response({'error': f'Station {station_id} not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check connection
        if not GatewayClient.is_station_connected(station_id):
            return Response(
                {'error': f'Station {station_id} is offline'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            result = GatewayClient.send_command(station_id, action, payload, timeout=30)
            return Response({'station_id': station_id, 'action': action, 'result': result})
        except TimeoutError as e:
            logger.warning(f"Command {action} to {station_id} timed out: {e}")
            return Response(
                {'error': f'Command timeout: {action}'},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except Exception as e:
            logger.error(f"Command {action} to {station_id} error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProvisioningView(APIView):
    """
    충전기 프로비저닝 엔드포인트.
    POST /config
    Body: {"serialNumber": "SIM-0001"}
    Response: {"cpId": "CP-SIM-0001", "wsUrl": "wss://chargeplus.kr/ocpp/1.6/CP-SIM-0001"}

    - 시리얼 번호로 등록된 충전기를 조회하여 cp_id와 WS URL을 반환한다.
    - 멱등성 보장: 동일 시리얼 재요청 시 기존 할당값 반환.
    - 미등록 시리얼: 404
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # JWT 미필요

    def post(self, request):
        serial_number = request.data.get('serialNumber', '').strip()
        if not serial_number:
            return Response(
                {'error': 'INVALID_REQUEST', 'message': 'serialNumber is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            station = ChargingStation.objects.get(serial_number=serial_number, is_active=True)
        except ChargingStation.DoesNotExist:
            return Response(
                {'error': 'NOT_FOUND', 'message': f'Serial number not registered: {serial_number}'},
                status=status.HTTP_404_NOT_FOUND,
            )

        ws_base = getattr(settings, 'CSMS_WS_BASE_URL', 'wss://chargeplus.kr/ocpp/1.6')
        cp_id = station.station_id
        ws_url = f'{ws_base}/{cp_id}'

        response_data = {'cpId': cp_id, 'wsUrl': ws_url}
        # already_provisioned 플래그: 이미 BootNotification을 수신한 적 있는 경우
        if station.last_boot_at is not None:
            response_data['alreadyProvisioned'] = True

        logger.info(f'Provisioning: serial={serial_number} → cpId={cp_id}')
        return Response(response_data, status=status.HTTP_200_OK)
