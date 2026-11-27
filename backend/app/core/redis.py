import logging
import time

import redis

from app.core.config import settings
from app.core.errors import APIError

log = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)


def rate_limit(key: str, limit: int, window_seconds: int, *, fail_closed: bool = False) -> None:
    """Fixed-window rate limit. Raises 429 when the limit is exceeded.

    If Redis is unavailable the request is allowed and a warning is logged, except for
    ``fail_closed`` limits (MFA and sign-in), which refuse rather than lose their protection.
    """
    bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds)
        count, _ = pipe.execute()
    except redis.RedisError:
        if fail_closed:
            log.error("rate limiter unavailable; refusing %s", key)
            raise APIError(
                503, "temporarily_unavailable", "Sign-in is briefly unavailable. Try again."
            ) from None
        log.warning("rate limiter unavailable; allowing request for %s", key)
        return
    if count > limit:
        raise APIError(429, "rate_limited", "Too many attempts. Please wait and try again.")


MFA_ATTEMPTS_PER_TOKEN = 5


def mfa_attempt_allowed(jti: str) -> bool:
    """Count a code attempt against one MFA token. False once it is used up or already used."""
    try:
        if redis_client.exists(f"mfa-used:{jti}"):
            return False
        pipe = redis_client.pipeline()
        pipe.incr(f"mfa-tries:{jti}")
        pipe.expire(f"mfa-tries:{jti}", 900)
        count, _ = pipe.execute()
    except redis.RedisError:
        raise APIError(
            503, "temporarily_unavailable", "Sign-in is briefly unavailable. Try again."
        ) from None
    return count <= MFA_ATTEMPTS_PER_TOKEN


def consume_mfa_token(jti: str) -> None:
    try:
        redis_client.set(f"mfa-used:{jti}", "1", ex=900)
    except redis.RedisError:
        log.warning("could not mark MFA token as used")
