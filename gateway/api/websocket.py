import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from broker.publisher import push_upstream, publish_downstream_response, set_station_connected, delete_station_connected
from broker.redis_client import get_redis
from broker.subscriber import listen_downstream
from config import settings
from core.connection_registry import registry
from core.exceptions import FORMATION_VIOLATION, INTERNAL_ERROR, NOT_IMPLEMENTED
from core.message_parser import (
    CALL, CALL_RESULT, CALL_ERROR,
    OcppMessage, parse,
    build_call_result, build_call_error,
)
from core.schema_validator import validate, has_schema

logger = logging.getLogger(__name__)

router = APIRouter()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def wait_for_upstream_response(msg_id: str, timeout: float) -> dict:
    """
    Subscribe to ocpp:response:{msg_id} and wait for the Celery worker to publish the response.
    """
    redis = get_redis()
    pubsub = redis.pubsub()

    try:
        await pubsub.subscribe(f"ocpp:response:{msg_id}")
        deadline = asyncio.get_event_loop().time() + timeout

        async for message in pubsub.listen():
            if asyncio.get_event_loop().time() > deadline:
                raise asyncio.TimeoutError()
            if message["type"] == "message":
                data = json.loads(message["data"])
                return data["payload"]

        raise asyncio.TimeoutError()
    finally:
        try:
            await pubsub.unsubscribe(f"ocpp:response:{msg_id}")
            await pubsub.aclose()
        except Exception:
            pass


async def handle_upstream(station_id: str, raw: str, ws: WebSocket) -> None:
    """
    Process a message received from the charge point (CP).
    - If it's a CALL_RESULT for a pending downstream command: resolve future and publish cmdresult
    - If it's a CALL (normal upstream message): validate, push to queue, wait for response
    """
    try:
        msg = parse(raw)
    except ValueError as e:
        logger.warning(f"Failed to parse message from {station_id}: {e}")
        # Cannot send error without msg_id; just log
        return

    if msg.msg_type == CALL_RESULT:
        # This is a CP response to a CSMS-initiated command
        if registry.has_pending_cmd(msg.msg_id):
            registry.resolve_pending_cmd(msg.msg_id, msg.payload)
            # Publish result back to Django GatewayClient
            await publish_downstream_response(msg.msg_id, msg.payload)
            logger.debug(f"Resolved downstream command result: msg_id={msg.msg_id}")
        else:
            logger.warning(f"Received CALL_RESULT with no pending command: msg_id={msg.msg_id}")
        return

    if msg.msg_type == CALL_ERROR:
        # CP sent an error response to a CSMS command
        if registry.has_pending_cmd(msg.msg_id):
            error_payload = {
                "error": True,
                "errorCode": msg.payload.get("errorCode", "GenericError"),
                "errorDescription": msg.payload.get("errorDescription", ""),
            }
            registry.resolve_pending_cmd(msg.msg_id, error_payload)
            await publish_downstream_response(msg.msg_id, error_payload)
        return

    if msg.msg_type != CALL:
        logger.warning(f"Unexpected message type {msg.msg_type} from {station_id}")
        return

    # --- Normal CALL (upstream: CP → CSMS) ---
    action = msg.action

    # Schema validation
    try:
        validate(action, msg.payload)
    except Exception as e:
        logger.warning(f"Schema validation failed for {action} from {station_id}: {e}")
        await ws.send_text(build_call_error(
            msg.msg_id, FORMATION_VIOLATION, str(e)
        ))
        return

    # Push to upstream queue for Celery processing
    upstream_data = {
        "station_id": station_id,
        "msg_id": msg.msg_id,
        "action": action,
        "payload": msg.payload,
        "received_at": utcnow_iso(),
    }

    try:
        await push_upstream(upstream_data)
    except Exception as e:
        logger.error(f"Failed to push upstream message to Redis: {e}")
        await ws.send_text(build_call_error(
            msg.msg_id, INTERNAL_ERROR, "Message queue unavailable"
        ))
        return

    # Wait for Celery worker to process and publish response
    try:
        response_payload = await asyncio.wait_for(
            wait_for_upstream_response(msg.msg_id, settings.RESPONSE_TIMEOUT),
            timeout=settings.RESPONSE_TIMEOUT + 1.0,
        )
        await ws.send_text(build_call_result(msg.msg_id, response_payload))
        logger.debug(f"Sent response for {action} (msg_id={msg.msg_id}) to {station_id}")
    except asyncio.TimeoutError:
        logger.warning(f"Timeout waiting for response to {action} (msg_id={msg.msg_id}) from {station_id}")
        await ws.send_text(build_call_error(
            msg.msg_id, INTERNAL_ERROR, "Handler timeout"
        ))
    except Exception as e:
        logger.error(f"Error processing upstream response for {action}: {e}")
        await ws.send_text(build_call_error(
            msg.msg_id, INTERNAL_ERROR, str(e)
        ))


@router.websocket("/ocpp/1.6/{station_id}")
async def ocpp_endpoint(station_id: str, websocket: WebSocket) -> None:
    """
    Main OCPP 1.6 WebSocket endpoint.
    Accepts connections with subprotocol 'ocpp1.6' and manages full message flow.
    """
    # Check requested subprotocol
    requested_protocols = websocket.headers.get("sec-websocket-protocol", "")
    if "ocpp1.6" not in requested_protocols:
        logger.warning(f"Station {station_id} requested unsupported subprotocol: {requested_protocols}")
        await websocket.close(code=1002, reason="Unsupported subprotocol")
        return

    # Accept WebSocket with ocpp1.6 subprotocol
    await websocket.accept(subprotocol="ocpp1.6")
    logger.info(f"Station {station_id} connected via WebSocket")

    # Register connection
    await registry.register(station_id, websocket)

    # Mark station as connected in Redis (TTL: 1 hour, deleted on disconnect)
    await set_station_connected(station_id, ttl=3600)

    # Start downstream listener task (CSMS → CP commands)
    downstream_task = asyncio.create_task(
        listen_downstream(station_id, websocket, registry)
    )

    try:
        async for raw_message in websocket.iter_text():
            logger.debug(f"Received from {station_id}: {raw_message[:200]}")
            await handle_upstream(station_id, raw_message, websocket)

    except WebSocketDisconnect as e:
        logger.info(f"Station {station_id} disconnected: code={e.code}")
    except Exception as e:
        logger.error(f"Unexpected error for station {station_id}: {e}")
    finally:
        # Cancel downstream listener
        downstream_task.cancel()
        try:
            await downstream_task
        except asyncio.CancelledError:
            pass

        # Unregister and clean up Redis
        await registry.unregister(station_id)
        await delete_station_connected(station_id)
        logger.info(f"Station {station_id} fully disconnected and cleaned up")
