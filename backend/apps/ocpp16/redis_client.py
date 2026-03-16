import redis as redis_lib
from django.conf import settings

_client = None


def get_redis() -> redis_lib.Redis:
    """
    Get the synchronous Redis client singleton.
    Used by Celery workers and Django views.
    """
    global _client
    if _client is None:
        _client = redis_lib.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=30,   # must be > brpop_timeout (default 5s) to avoid false TimeoutError
            retry_on_timeout=True,
        )
    return _client
