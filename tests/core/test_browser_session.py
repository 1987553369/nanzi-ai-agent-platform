import pytest

from app.services.browser_session_service import BrowserSessionService


pytestmark = pytest.mark.no_infrastructure


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex):
        self.values[key] = (value, ex)

    async def get(self, key):
        item = self.values.get(key)
        return item[0] if item else None

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_browser_session_round_trip_keeps_api_key_out_of_token(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis():
        return redis

    monkeypatch.setattr("app.services.browser_session_service.get_redis", fake_get_redis)
    token = await BrowserSessionService.create("long-lived-api-key", 3600)

    assert "long-lived-api-key" not in token
    assert await BrowserSessionService.resolve_api_key(token) == "long-lived-api-key"
    stored_value, ttl = next(iter(redis.values.values()))
    assert "long-lived-api-key" not in stored_value
    assert ttl == 3600


@pytest.mark.asyncio
async def test_browser_session_revoke_invalidates_token(monkeypatch):
    redis = FakeRedis()

    async def fake_get_redis():
        return redis

    monkeypatch.setattr("app.services.browser_session_service.get_redis", fake_get_redis)
    token = await BrowserSessionService.create("long-lived-api-key", 3600)
    await BrowserSessionService.revoke(token)

    assert await BrowserSessionService.resolve_api_key(token) is None
