"""Redis-backed fixed-window rate limiting for sensitive API operations."""

import hashlib
import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.core.config import settings


logger = logging.getLogger(__name__)

_INCREMENT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


def _rate_limit_key(bucket: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    safe_bucket = "".join(ch for ch in bucket if ch.isalnum() or ch in {"-", "_"})
    return f"rate_limit:{safe_bucket or 'default'}:{digest}"


async def enforce_rate_limit(
    *,
    bucket: str,
    identifier: str,
    limit: int,
    window_seconds: int,
    redis_client: Optional[Any] = None,
    fail_closed: Optional[bool] = None,
) -> None:
    if limit <= 0 or window_seconds <= 0:
        raise ValueError("限流阈值和窗口必须大于 0")

    if redis_client is None:
        from app.core.redis import get_redis

        try:
            redis_client = await get_redis()
        except Exception:
            redis_client = None
            logger.exception("Rate limit Redis connection failed for bucket %s", bucket)

    should_fail_closed = (
        settings.API_SERVICE_ENV.strip().lower() in {"prod", "production"}
        if fail_closed is None
        else fail_closed
    )
    if redis_client is None:
        if should_fail_closed:
            raise HTTPException(status_code=503, detail="限流服务暂时不可用")
        return

    try:
        current, ttl = await redis_client.eval(
            _INCREMENT_SCRIPT,
            1,
            _rate_limit_key(bucket, identifier),
            int(window_seconds),
        )
    except Exception as exc:
        logger.exception("Rate limit check failed for bucket %s", bucket)
        if should_fail_closed:
            raise HTTPException(status_code=503, detail="限流服务暂时不可用") from exc
        return

    if int(current) > limit:
        retry_after = max(1, int(ttl) if int(ttl) > 0 else int(window_seconds))
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
