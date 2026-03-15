import json
import logging
import time
import uuid

from apps.ocpp16.redis_client import get_redis

logger = logging.getLogger(__name__)


class GatewayClient:
    """
    Client for sending OCPP commands from Django to the FastAPI Gateway.
    Commands are published to Redis and the Gateway forwards them to the charge point.
    """

    @staticmethod
    def send_command(station_id: str, action: str, payload: dict, timeout: int = 30) -> dict:
        """
        Send a command synchronously and wait for the charge point's response.

        Flow:
          1. Generate msg_id
          2. Set tracking key in Redis
          3. Publish command to ocpp:downstream:{station_id}
          4. Subscribe to ocpp:cmdresult:{msg_id}
          5. Return response or raise TimeoutError

        Args:
            station_id: Charge point identifier
            action: OCPP action name (e.g., 'Reset', 'RemoteStartTransaction')
            payload: OCPP action payload
            timeout: Maximum wait time in seconds

        Returns:
            dict: The charge point's response payload

        Raises:
            TimeoutError: If the charge point doesn't respond within timeout
        """
        msg_id = str(uuid.uuid4())
        r = get_redis()

        # Register tracking key (TTL = timeout)
        r.set(f"ocpp:pending:{msg_id}", action, ex=timeout)

        # Publish command to Gateway for forwarding to CP
        r.publish(
            f"ocpp:downstream:{station_id}",
            json.dumps({
                "msg_id": msg_id,
                "action": action,
                "payload": payload,
            })
        )
        logger.info(f"Sent command {action} to {station_id} (msg_id={msg_id})")

        # Subscribe and wait for CP response
        pubsub = r.pubsub()
        pubsub.subscribe(f"ocpp:cmdresult:{msg_id}")
        deadline = time.time() + timeout

        try:
            for message in pubsub.listen():
                if time.time() > deadline:
                    break
                if message["type"] == "message":
                    result = json.loads(message["data"])
                    logger.info(f"Received response for {action} from {station_id}: {result}")
                    return result
        finally:
            try:
                pubsub.unsubscribe(f"ocpp:cmdresult:{msg_id}")
                pubsub.close()
            except Exception:
                pass
            # Clean up pending key
            r.delete(f"ocpp:pending:{msg_id}")

        raise TimeoutError(f"Command {action} to {station_id} timed out after {timeout}s")

    @staticmethod
    def send_command_async(station_id: str, action: str, payload: dict) -> str:
        """
        Send a command without waiting for a response.
        Returns the msg_id for reference.
        Useful for fire-and-forget commands like UpdateFirmware.
        """
        msg_id = str(uuid.uuid4())
        r = get_redis()

        r.publish(
            f"ocpp:downstream:{station_id}",
            json.dumps({
                "msg_id": msg_id,
                "action": action,
                "payload": payload,
            })
        )
        logger.info(f"Sent async command {action} to {station_id} (msg_id={msg_id})")
        return msg_id

    @staticmethod
    def is_station_connected(station_id: str) -> bool:
        """Check if a charging station is currently connected to the Gateway."""
        r = get_redis()
        return r.exists(f"ocpp:connected:{station_id}") > 0
