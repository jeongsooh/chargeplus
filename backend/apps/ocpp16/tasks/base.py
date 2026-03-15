import json
import logging

from apps.ocpp16.redis_client import get_redis

logger = logging.getLogger(__name__)


def publish_response(msg_id: str, payload: dict) -> None:
    """
    Publish a response payload to ocpp:response:{msg_id}.
    The FastAPI Gateway subscribed to this channel will receive it
    and forward the CALL_RESULT to the charge point.
    """
    r = get_redis()
    r.publish(
        f"ocpp:response:{msg_id}",
        json.dumps({"msg_id": msg_id, "payload": payload})
    )
    logger.debug(f"Published response for msg_id={msg_id}: {payload}")


def log_ocpp_message(
    station_id: str,
    msg_id: str,
    direction: int,
    action: str,
    payload: dict,
) -> None:
    """
    Save an OCPP message to the audit log (OcppMessage model).
    Failures are logged but do not raise exceptions.
    """
    from apps.ocpp16.models import OcppMessage
    try:
        OcppMessage.objects.create(
            station_id=station_id,
            msg_id=msg_id,
            direction=direction,
            action=action,
            payload=payload,
        )
    except Exception as e:
        logger.error(f"Failed to log OCPP message (station={station_id}, action={action}): {e}")
