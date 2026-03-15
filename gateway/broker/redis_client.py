import logging
from redis.asyncio import Redis, from_url

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


async def init_redis(url: str) -> None:
    """Initialize the async Redis connection pool."""
    global _redis_client
    _redis_client = await from_url(url, encoding="utf-8", decode_responses=True)
    logger.info(f"Redis connection initialized: {url}")


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed.")


def get_redis() -> Redis:
    """Get the initialized Redis client. Must call init_redis() first."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client
