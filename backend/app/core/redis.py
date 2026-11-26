import logging
import time

import redis

from app.core.config import settings
from app.core.errors import APIError

log = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)


def rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Fixed-window rate limit. Raises 429 when the limit is exceeded.

    If Redis is unavailable the request is allowed and a warning is logged; per-account
    lockout in the database still protects sign-in.
    """
    bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds)
        count, _ = pipe.execute()
    except redis.RedisError:
        log.warning("rate limiter unavailable; allowing request for %s", key)
        return
    if count > limit:
        raise APIError(429, "rate_limited", "Too many attempts. Please wait and try again.")
