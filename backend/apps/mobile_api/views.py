import logging
import time

from django.contrib.auth import authenticate
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.config.models import CsmsVariable

logger = logging.getLogger(__name__)


class LoginView(APIView):
    """
    POST /api/login
    Authenticate user and return JWT access token.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user_id = request.data.get("user_id", "")
        password = request.data.get("password", "")

        if not user_id or not password:
            return Response(
                {"detail": "아이디와 비밀번호를 입력해주세요."},
                status=http_status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(username=user_id, password=password)
        if not user:
            return Response(
                {"detail": "아이디 또는 비밀번호가 틀렸습니다."},
                status=http_status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "비활성화된 계정입니다."},
                status=http_status.HTTP_401_UNAUTHORIZED,
            )

        token = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "token": str(token.access_token),
        })


class ChargeStartView(APIView):
    """
    POST /api/charge/start?qr_code={station_id}
    Initiate a charging session via QR code scan.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.stations.models import ChargingStation, Connector
        from apps.mobile_api.models import AppSession
        from apps.ocpp16.services.gateway_client import GatewayClient
        from apps.ocpp16.tasks.core import check_pending_session_timeout
        from rest_framework import status

        station_id = request.query_params.get("qr_code", "").strip()
        if not station_id:
            return Response(
                {"error": "qr_code 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        goal_type = request.query_params.get("goal_type", "free").strip().lower()
        if goal_type not in AppSession.GoalType.values:
            return Response(
                {"error": f"goal_type은 {AppSession.GoalType.values} 중 하나여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        goal_value_str = request.query_params.get("goal_value", "").strip()
        if goal_type != AppSession.GoalType.FREE:
            if not goal_value_str:
                return Response(
                    {"error": f"goal_type이 '{goal_type}'일 때 goal_value는 필수입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                goal_value = float(goal_value_str)
                if goal_value <= 0:
                    raise ValueError
            except ValueError:
                return Response(
                    {"error": "goal_value는 0보다 큰 숫자여야 합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            goal_value = None

        user = request.user

        # 1. Find station
        try:
            station = ChargingStation.objects.get(station_id=station_id, is_active=True)
        except ChargingStation.DoesNotExist:
            return Response(
                {"error": "존재하지 않는 충전기입니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. Check station online status
        if not GatewayClient.is_station_connected(station_id):
            return Response(
                {"error": "충전기가 오프라인입니다."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # 3. Check for existing active/pending session
        duplicate = AppSession.objects.filter(
            charging_station=station,
            status__in=[AppSession.Status.PENDING, AppSession.Status.ACTIVE],
        ).exists()
        if duplicate:
            return Response(
                {"error": "이미 충전 중인 세션이 있습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        # 4. Find available connector
        connector = Connector.objects.filter(
            evse__charging_station=station,
            current_status=Connector.Status.AVAILABLE,
        ).first()
        if not connector:
            return Response(
                {"error": "사용 가능한 커넥터가 없습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        # 5. Create AppSession
        session_id = f"session_{int(time.time())}_{station_id}"
        session = AppSession.objects.create(
            session_id=session_id,
            user=user,
            charging_station=station,
            connector_id=connector.connector_id,
            status=AppSession.Status.PENDING,
            goal_type=goal_type,
            goal_value=goal_value,
        )

        # 6. Send RemoteStartTransaction to CP
        id_tag = f"APP-{user.pk}"
        try:
            result = GatewayClient.send_command(
                station_id,
                "RemoteStartTransaction",
                {
                    "idTag": id_tag,
                    "connectorId": connector.connector_id,
                },
                timeout=10,
            )

            if result.get('status') == 'Rejected':
                # CP rejected the command
                AppSession.objects.filter(pk=session.pk).update(
                    status=AppSession.Status.FAILED,
                    fail_reason='충전기가 원격 충전을 거부했습니다.',
                )
                return Response(
                    {"error": "충전기가 원격 충전을 거부했습니다."},
                    status=status.HTTP_409_CONFLICT,
                )

        except TimeoutError:
            # CP didn't respond; session stays pending with timeout task
            logger.warning(f"RemoteStartTransaction timed out for {station_id}")
        except Exception as e:
            logger.error(f"RemoteStartTransaction error for {station_id}: {e}")
            AppSession.objects.filter(pk=session.pk).update(
                status=AppSession.Status.FAILED,
                fail_reason='충전기 통신 오류가 발생했습니다.',
            )
            return Response(
                {"error": "충전기 통신 오류가 발생했습니다."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # 7. Schedule pending session timeout check
        timeout_seconds = int(CsmsVariable.get("pending_session_timeout", default=120))
        check_pending_session_timeout.apply_async(
            args=[session_id],
            countdown=timeout_seconds,
        )

        logger.info(
            f"Charge start: user={user.pk} station={station_id} "
            f"connector={connector.connector_id} session={session_id} "
            f"goal={goal_type}:{goal_value}"
        )

        return Response({
            "success": True,
            "sessionId": session_id,
        })


class ChargeStatusView(APIView):
    """
    GET /api/charge/status?session_id={session_id}
    Poll charging session status (app polls every ~3 seconds).
    Returns 404 when session is stopped (app shows completion screen).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.mobile_api.models import AppSession
        from rest_framework import status

        session_id = request.query_params.get("session_id", "").strip()
        if not session_id:
            return Response(
                {"error": "session_id 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = AppSession.objects.get(session_id=session_id)
        except AppSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Verify ownership
        if session.user != request.user:
            raise PermissionDenied("이 세션에 접근할 권한이 없습니다.")

        # Stopped sessions return 404 (app transitions to completion screen)
        if session.status == AppSession.Status.STOPPED:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Build response based on status
        if session.status == AppSession.Status.PENDING:
            return Response({
                "status": "pending",
                "kwh": 0.0,
                "reason": None,
            })
        elif session.status == AppSession.Status.ACTIVE:
            return Response({
                "status": "active",
                "kwh": float(session.kwh_current),
                "reason": None,
            })
        elif session.status == AppSession.Status.FAILED:
            return Response({
                "status": "failed",
                "kwh": 0.0,
                "reason": session.fail_reason or "충전 세션이 실패했습니다.",
            })
        else:
            return Response({
                "status": session.status,
                "kwh": float(session.kwh_current),
                "reason": None,
            })


class ChargeStopView(APIView):
    """
    POST /api/charge/stop?session_id={session_id}
    Stop the charging session and return final results.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.mobile_api.models import AppSession
        from apps.ocpp16.services.gateway_client import GatewayClient
        from rest_framework import status
        import time as time_module

        session_id = request.query_params.get("session_id", "").strip()
        if not session_id:
            return Response(
                {"error": "session_id 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = AppSession.objects.get(session_id=session_id)
        except AppSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Verify ownership
        if session.user != request.user:
            raise PermissionDenied("이 세션에 접근할 권한이 없습니다.")

        # Already stopped
        if session.status == AppSession.Status.STOPPED:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Handle failed sessions (no transaction started)
        if session.status == AppSession.Status.FAILED:
            # Clean up: mark as dealt with (keep record but respond OK)
            logger.info(f"Stop requested on failed session {session_id}")
            return Response({
                "success": True,
                "kwh": 0.0,
                "cost": 0,
                "currency": "KRW",
                "message": "세션이 시작되지 않았습니다.",
            })

        # Handle pending sessions (never started)
        if session.status == AppSession.Status.PENDING:
            AppSession.objects.filter(pk=session.pk).update(
                status=AppSession.Status.FAILED,
                fail_reason='사용자가 충전을 취소했습니다.',
            )
            return Response({
                "success": False,
                "error": "충전이 아직 시작되지 않았습니다.",
            }, status=status.HTTP_409_CONFLICT)

        # Active session: send RemoteStopTransaction
        if session.status == AppSession.Status.ACTIVE:
            if not session.transaction:
                logger.error(f"Active session {session_id} has no transaction")
                return Response(
                    {"error": "트랜잭션을 찾을 수 없습니다."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            station_id = session.charging_station.station_id

            try:
                result = GatewayClient.send_command(
                    station_id,
                    "RemoteStopTransaction",
                    {"transactionId": session.transaction.transaction_id},
                    timeout=30,
                )
                logger.info(
                    f"RemoteStopTransaction result for session {session_id}: "
                    f"{result.get('status')}"
                )
            except TimeoutError:
                logger.warning(f"RemoteStopTransaction timed out for session {session_id}")
            except Exception as e:
                logger.error(f"RemoteStopTransaction error for session {session_id}: {e}")

            # Wait for StopTransaction to be processed (AppSession updated to 'stopped')
            max_wait = 35  # seconds
            poll_interval = 0.5
            elapsed = 0.0

            while elapsed < max_wait:
                time_module.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    session.refresh_from_db()
                except AppSession.DoesNotExist:
                    break

                if session.status == AppSession.Status.STOPPED:
                    break

            # Final response
            if session.status == AppSession.Status.STOPPED:
                return Response({
                    "success": True,
                    "kwh": float(session.final_kwh or 0),
                    "cost": session.final_cost or 0,
                    "currency": "KRW",
                    "message": "충전이 완료되었습니다. 이용해 주셔서 감사합니다.",
                })
            else:
                # StopTransaction not yet processed; return current values
                return Response({
                    "success": True,
                    "kwh": float(session.kwh_current),
                    "cost": 0,
                    "currency": "KRW",
                    "message": "충전 종료 처리 중입니다.",
                })

        return Response(
            {"error": "유효하지 않은 세션 상태입니다."},
            status=status.HTTP_409_CONFLICT,
        )
