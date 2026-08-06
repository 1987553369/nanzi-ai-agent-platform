"""Opaque browser sessions backed by Redis; long-lived API keys stay server-side."""

import hashlib
import secrets
from typing import Optional

from app.core.redis import get_redis
from app.utils.encryption import get_api_key_manager


class BrowserSessionService:
    COOKIE_NAME = "nanzi_session"
    KEY_PREFIX = "auth:browser_session"

    @classmethod
    def _redis_key(cls, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{cls.KEY_PREFIX}:{digest}"

    @classmethod
    async def create(cls, api_key: str, ttl_seconds: int) -> str:
        redis = await get_redis()
        if redis is None:
            raise RuntimeError("浏览器会话服务暂时不可用")
        token = secrets.token_urlsafe(32)
        encrypted_api_key = get_api_key_manager().encrypt_api_key(api_key)
        await redis.set(cls._redis_key(token), encrypted_api_key, ex=ttl_seconds)
        return token

    @classmethod
    async def resolve_api_key(cls, token: Optional[str]) -> Optional[str]:
        normalized = str(token or "").strip()
        if not normalized:
            return None
        redis = await get_redis()
        if redis is None:
            return None
        encrypted_api_key = await redis.get(cls._redis_key(normalized))
        if not encrypted_api_key:
            return None
        try:
            return get_api_key_manager().decrypt_api_key(encrypted_api_key)
        except ValueError:
            await redis.delete(cls._redis_key(normalized))
            return None

    @classmethod
    async def revoke(cls, token: Optional[str]) -> None:
        normalized = str(token or "").strip()
        if not normalized:
            return
        redis = await get_redis()
        if redis is not None:
            await redis.delete(cls._redis_key(normalized))
