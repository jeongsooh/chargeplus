import json
import logging
from .redis_client import get_redis

logger = logging.getLogger(__name__)


async def push_upstream(data: dict) -> None:
    """
    Push a message to the ocpp:upstream Redis list queue.
    The Django dispatcher will BRPOP from this queue and dispatch to Celery workers.
    """
    redis = get_redis()
    payload = json.dumps(data, ensure_ascii=False)
    await redis.lpush("ocpp:upstream", payload)
    logger.debug(f"Pushed to ocpp:upstream: station={data.get('station_id')} action={data.get('action')}")


async def publish_downstream_response(msg_id: str, payload: dict) -> None:
    """
    Publish a CP's response to a downstream command on ocpp:cmdresult:{msg_id}.
    The Django GatewayClient waiting on pubsub will receive this.
    """
    redis = get_redis()
    message = json.dumps(payload, ensure_ascii=False)
    await redis.publish(f"ocpp:cmdresult:{msg_id}", message)
    logger.debug(f"Published cmdresult for msg_id={msg_id}")


async def set_station_connected(station_id: str, ttl: int = 3600) -> None:
    """Mark a station as connected in Redis with TTL (refreshed by gateway keepalive)."""
    redis = get_redis()
    await redis.set(f"ocpp:connected:{station_id}", "1", ex=ttl)


async def delete_station_connected(station_id: str) -> None:
    """Remove station's connected key from Redis."""
    redis = get_redis()
    await redis.delete(f"ocpp:connected:{station_id}")


async def refresh_station_connected(station_id: str, ttl: int = 180) -> None:
    """Refresh the TTL of station's connected key."""
    redis = get_redis()
    await redis.expire(f"ocpp:connected:{station_id}", ttl)
