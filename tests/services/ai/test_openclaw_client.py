import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.openclaw_client import (
    OpenClawClient,
    summarize_openclaw_payload_for_log,
)


class _AsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@pytest.fixture(scope="function", autouse=True)
async def init_infrastructure():
    """Override global infrastructure initialization; this test only covers payload summarization."""
    with patch("app.core.database.init_db", new_callable=AsyncMock), \
         patch("app.core.database.close_db", new_callable=AsyncMock), \
         patch("app.core.redis.init_redis", new_callable=AsyncMock), \
         patch("app.core.redis.close_redis", new_callable=AsyncMock), \
         patch("app.core.orm.AsyncSessionLocal", new_callable=MagicMock):
        yield


def test_openclaw_payload_log_summary_omits_message_content_and_auth_context():
    payload = {
        "model": "openclaw-v1",
        "stream": True,
        "user": "chenxiaolong-session",
        "conversation_id": "conv-1",
        "messages": [
            {"role": "system", "content": "<AUTH_CONTEXT>{\"datasets\":[{\"name\":\"secret\"}]}</AUTH_CONTEXT>"},
            {"role": "user", "content": "查一下敏感数据"},
        ],
        "extra_params": {"x": 1},
    }

    summary = summarize_openclaw_payload_for_log(payload)

    assert summary == {
        "model": "openclaw-v1",
        "stream": True,
        "message_count": 2,
        "extra_param_keys": ["x"],
    }
    assert "messages" not in summary
    assert "user" not in summary
    assert "conversation_id" not in summary
    assert "secret" not in str(summary)


@pytest.mark.asyncio
async def test_openclaw_stored_key_is_not_sent_to_override_origin():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }
    http_client = AsyncMock()
    http_client.post.return_value = response

    async def config_get(key):
        return {
            "openclaw_api_url": "https://trusted-openclaw.example/api",
            "openclaw_api_key": "stored-secret",
        }.get(key)

    with patch(
        "app.services.ai.openclaw_client.ConfigService.get",
        side_effect=config_get,
    ), patch(
        "app.services.ai.openclaw_client.create_integration_outbound_client",
        return_value=_AsyncClientContext(http_client),
    ):
        chunks = [
            chunk
            async for chunk in OpenClawClient().chat_stream(
                query="hello",
                history=[],
                config={
                    "base_url": "https://attacker.example/api",
                    "stream": False,
                },
            )
        ]

    assert chunks == [{"type": "answer", "content": "ok"}]
    request_headers = http_client.post.await_args.kwargs["headers"]
    assert "Authorization" not in request_headers


@pytest.mark.asyncio
async def test_openclaw_unapproved_private_override_fails_before_request():
    async def config_get(key):
        return {
            "openclaw_api_url": "https://trusted-openclaw.example/api",
            "openclaw_api_key": "stored-secret",
        }.get(key)

    with patch(
        "app.services.ai.openclaw_client.ConfigService.get",
        side_effect=config_get,
    ), patch(
        "app.services.ai.openclaw_client.create_integration_outbound_client",
    ) as client_factory:
        chunks = [
            chunk
            async for chunk in OpenClawClient().chat_stream(
                query="hello",
                history=[],
                config={
                    "base_url": "http://10.20.1.8:8080",
                    "stream": False,
                },
            )
        ]

    assert chunks == [
        {
            "type": "error",
            "content": "OpenClaw API URL is not approved by outbound policy.",
        }
    ]
    client_factory.assert_not_called()
