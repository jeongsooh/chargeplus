import asyncio
import json
import logging

from fastapi import WebSocket

from .redis_client import get_redis
from .publisher import publish_downstream_response
from core.connection_registry import ConnectionRegistry
from core.message_parser import build_call

logger = logging.getLogger(__name__)


async def listen_downstream(station_id: str, ws: WebSocket, registry: ConnectionRegistry) -> None:
    """
    Subscribe to ocpp:downstream:{station_id} and forward CSMS commands to the charge point.
    Each received command is sent as a CALL [2, msg_id, action, payload] to the WebSocket.
    The pending future is tracked in the registry so upstream handler can resolve it.
    """
    redis = get_redis()
    pubsub = redis.pubsub()

    try:
        await pubsub.subscribe(f"ocpp:downstream:{station_id}")
        logger.info(f"Subscribed to ocpp:downstream:{station_id}")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                msg_id = data["msg_id"]
                action = data["action"]
                payload = data["payload"]

                # Build CALL frame and send to charge point
                call_frame = build_call(msg_id, action, payload)
                sent = await registry.send(station_id, call_frame)

                if not sent:
                    logger.warning(f"Could not send downstream command to {station_id}: not connected")
                    # Publish error result so Django doesn't hang
                    await publish_downstream_response(msg_id, {"error": "Station disconnected"})
                    break

                # Create a future to capture the CP's response
                loop = asyncio.get_event_loop()
                future = loop.create_future()
                registry.set_pending_cmd(msg_id, future)

                logger.debug(f"Sent downstream command {action} (msg_id={msg_id}) to {station_id}")

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in downstream message for {station_id}: {e}")
            except KeyError as e:
                logger.error(f"Missing key in downstream message for {station_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing downstream message for {station_id}: {e}")

    except asyncio.CancelledError:
        logger.info(f"Downstream listener for {station_id} cancelled.")
    except Exception as e:
        logger.error(f"Downstream listener error for {station_id}: {e}")
    finally:
        try:
            await pubsub.unsubscribe(f"ocpp:downstream:{station_id}")
            await pubsub.aclose()
        except Exception:
            pass
