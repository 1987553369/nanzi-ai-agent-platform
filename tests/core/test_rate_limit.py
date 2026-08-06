import pytest
from fastapi import HTTPException

from app.core.rate_limit import enforce_rate_limit


pytestmark = pytest.mark.no_infrastructure


class FakeRedis:
    def __init__(self, result=None, error=None):
        self.result = result or [1, 60]
        self.error = error
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_rate_limit_uses_hashed_identifier_and_allows_within_limit():
    client = FakeRedis([3, 41])

    await enforce_rate_limit(
        bucket="login",
        identifier="user@example.com",
        limit=10,
        window_seconds=60,
        redis_client=client,
    )

    key = client.calls[0][2]
    assert "user@example.com" not in key
    assert key.startswith("rate_limit:login:")


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_retry_after():
    client = FakeRedis([11, 37])

    with pytest.raises(HTTPException) as caught:
        await enforce_rate_limit(
            bucket="login",
            identifier="user-1",
            limit=10,
            window_seconds=60,
            redis_client=client,
        )

    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "37"}


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_when_redis_is_unavailable_in_production():
    with pytest.raises(HTTPException) as caught:
        await enforce_rate_limit(
            bucket="login",
            identifier="user-1",
            limit=10,
            window_seconds=60,
            redis_client=FakeRedis(error=ConnectionError("down")),
            fail_closed=True,
        )

    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_rate_limit_degrades_open_for_development():
    await enforce_rate_limit(
        bucket="login",
        identifier="user-1",
        limit=10,
        window_seconds=60,
        redis_client=FakeRedis(error=ConnectionError("down")),
        fail_closed=False,
    )


@pytest.mark.asyncio
async def test_rate_limit_rejects_invalid_policy():
    with pytest.raises(ValueError, match="必须大于 0"):
        await enforce_rate_limit(
            bucket="login",
            identifier="user-1",
            limit=0,
            window_seconds=60,
            redis_client=FakeRedis(),
        )
