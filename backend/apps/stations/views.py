import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
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
