import logging

from apps.config.models import CsmsVariable

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles user and admin notifications."""

    @staticmethod
    def send_charge_complete(user_phone: str, kwh: float, cost: int, station_id: str) -> None:
        """
        Send a charge completion notification to the user.
        Currently logs; implement Kakao/SMS integration here.
        """
        if not CsmsVariable.get("notification_enabled", default=True):
            return

        logger.info(
            f"[NOTIFY] Charge complete: station={station_id} "
            f"user_phone={user_phone} kwh={kwh:.3f} cost={cost}KRW"
        )
        # TODO: integrate Kakao 알림톡 API
        # Example:
        # from apps.integrations.kakao import send_kakao_notification
        # send_kakao_notification(
        #     phone=user_phone,
        #     template='charge_complete',
        #     params={'kwh': f'{kwh:.2f}', 'cost': str(cost), 'station_id': station_id}
        # )

    @staticmethod
    def send_error_alert(station_id: str, connector_id: int, error_code: str) -> None:
        """
        Send an error alert to administrators when a station fault is detected.
        """
        if not CsmsVariable.get("notification_error_enabled", station_id=station_id, default=True):
            return

        logger.warning(
            f"[NOTIFY] Station error: station={station_id} "
            f"connector={connector_id} error={error_code}"
        )
        # TODO: integrate Kakao 알림톡 / SMS for admin alerts
        # Example:
        # admin_phone = CsmsVariable.get("admin_phone", default="")
        # if admin_phone:
        #     send_sms(phone=admin_phone, message=f"Station {station_id} error: {error_code}")

    @staticmethod
    def send_session_failed(user_phone: str, station_id: str, reason: str) -> None:
        """Notify user that their charging session failed to start."""
        if not CsmsVariable.get("notification_enabled", default=True):
            return

        logger.info(
            f"[NOTIFY] Session failed: station={station_id} "
            f"user_phone={user_phone} reason={reason}"
        )
        # TODO: Kakao/SMS notification
