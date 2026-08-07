import asyncio
from pathlib import Path

import httpx

from app.utils.model_providers import (
    create_model_outbound_client,
    is_trusted_local_ollama_url,
)
from app.utils.outbound_url_policy import ResolvedIPTransport
from app.utils.outbound_url_policy import redact_outbound_url_for_log


ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_user_controlled_http_paths_use_pinned_clients():
    required_factory_by_file = {
        "app/services/ai/tools/system_tools.py": "create_ssrf_safe_async_client",
        "app/services/ai/tools/generic_api.py": "create_ssrf_safe_async_client",
        "app/services/notification_service.py": "create_ssrf_safe_async_client",
        "app/services/ai/tools/advanced_auxiliary_tools.py": "get_with_ssrf_safe_redirects",
        "app/services/ai/embedding_client.py": "create_model_outbound_client",
        "app/api/portal/endpoints/models.py": "create_model_outbound_client",
        "app/api/portal/endpoints/system.py": "create_ssrf_safe_async_client",
    }
    for path, required_factory in required_factory_by_file.items():
        assert required_factory in _source(path), path


def test_notification_and_scheduler_paths_have_no_direct_http_client():
    for path in (
        "app/services/notification_service.py",
        "app/services/ai/tools/notification_tools.py",
        "app/services/ai/scheduler_service.py",
        "app/services/ai/tools/generic_api.py",
        "app/services/ai/tools/system_tools.py",
    ):
        assert "httpx.AsyncClient(" not in _source(path), path


def test_managed_integrations_use_scoped_outbound_clients():
    for path in (
        "app/services/ai/ragflow_client.py",
        "app/services/ai/openclaw_client.py",
        "app/services/ai/tools/data_api.py",
        "app/api/portal/endpoints/ragflow.py",
    ):
        source = _source(path)
        assert "create_integration_outbound_client" in source, path
        assert "httpx.AsyncClient(" not in source, path

    assert not (ROOT / "app/core/http_client.py").exists()


def test_managed_integration_secrets_are_origin_bound():
    ragflow_source = _source("app/services/ai/ragflow_client.py")
    openclaw_source = _source("app/services/ai/openclaw_client.py")
    portal_source = _source("app/api/portal/endpoints/ragflow.py")

    assert "integration_urls_share_origin" in ragflow_source
    assert "不能发送到其他 Origin" in ragflow_source
    assert "integration_urls_share_origin" in openclaw_source
    assert "integration_urls_share_origin" in portal_source
    assert "不能发送到其他 Origin" in portal_source


def test_managed_integration_logs_omit_request_secrets_and_values():
    data_api_source = _source("app/services/ai/tools/data_api.py")
    openclaw_source = _source("app/services/ai/openclaw_client.py")

    assert "RAGFlow Headers: Authorization" not in data_api_source
    assert "RAGFlow Payload:" not in data_api_source
    assert '"user": payload.get("user")' not in openclaw_source
    assert '"conversation_id": payload.get("conversation_id")' not in openclaw_source


def test_dynamic_browser_url_entry_is_fail_closed_until_isolated():
    source = _source("app/services/ai/tools/advanced_auxiliary_tools.py")
    assert "动态浏览器抓取暂未开放" in source
    assert "await page.goto(url" not in source


def test_model_stored_secret_is_bound_to_provider_and_origin():
    source = _source("app/api/portal/endpoints/models.py")
    assert "_assert_stored_model_key_audience" in source
    assert "已保存的 API Key 不能跨 Provider 复用" in source
    assert "已保存的 API Key 不能发送到其他 Origin" in source


def test_only_fixed_local_ollama_authority_bypasses_public_ip_policy():
    assert is_trusted_local_ollama_url(
        "ollama",
        "http://localhost:11434/v1/models",
    )
    assert not is_trusted_local_ollama_url(
        "ollama",
        "http://127.0.0.1:11434/v1/models",
    )
    assert not is_trusted_local_ollama_url(
        "other",
        "http://localhost:11434/v1/models",
    )
    assert not is_trusted_local_ollama_url(
        "ollama",
        "http://localhost:8080/v1/models",
    )

    public_client = create_model_outbound_client(
        provider="other",
        request_url="https://models.example/v1/models",
        timeout=1.0,
    )
    local_client = create_model_outbound_client(
        provider="ollama",
        request_url="http://localhost:11434/v1/models",
        timeout=1.0,
    )
    try:
        assert isinstance(public_client._transport, ResolvedIPTransport)
        assert isinstance(local_client._transport, httpx.AsyncHTTPTransport)
        assert local_client.follow_redirects is False
    finally:
        asyncio.run(public_client.aclose())
        asyncio.run(local_client.aclose())


def test_outbound_log_url_redacts_query_and_userinfo():
    assert (
        redact_outbound_url_for_log(
            "https://user:secret@example.com:8443/api?access_token=secret"
        )
        == "https://example.com:8443"
    )
