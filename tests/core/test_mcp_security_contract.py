from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mcp_response_does_not_inherit_write_credentials():
    endpoint = _source("app/api/portal/endpoints/mcp.py")

    assert "class McpServerResponse(BaseModel):" in endpoint
    response_block = endpoint.split("class McpServerResponse", 1)[1].split("class McpToolResponse", 1)[0]
    assert "\n    auth_headers:" not in response_block
    assert "has_auth_headers" in response_block
    assert "credential_status" in response_block


def test_mcp_client_redacts_credentials_and_disables_redirects():
    client = _source("app/services/ai/tools/mcp_client.py")

    assert "Auth Value" not in client
    assert "Sending Authorization" not in client
    assert "follow_redirects=True" not in client
    assert "create_ssrf_safe_async_client" in client
    assert "httpx.AsyncClient(" not in client
    assert "allowed_url=self.sse_url" in client
    assert "allowed_url=session_mgr.sse_url" in client
    assert "except OutboundUrlPolicyError:" in client
    assert "httpx_client_factory" in client
    assert "client.stream(" in client
    assert "await client.get(" not in client


def test_mcp_frontend_preserves_secret_without_server_echo():
    registry = _source("frontend/src/components/system/McpServerRegistry.vue")

    assert "server.auth_headers" not in registry
    assert "server.has_auth_headers" in registry
    assert "delete payload.auth_headers" in registry
    assert "authHeadersDirty" in registry
    assert "existingAuthHeadersConfigured.value && !authHeadersDirty.value" in registry
    assert 'type="password"' in registry
    assert "credentialNeedsAttention" in registry
    assert "历史认证信息已隔离" in registry


def test_mcp_runtime_has_no_plaintext_credential_fallback():
    credentials = _source("app/utils/mcp_credentials.py")
    client = _source("app/services/ai/tools/mcp_client.py")
    endpoint = _source("app/api/portal/endpoints/mcp.py")

    assert "return parse_mcp_auth_headers(normalized)" not in credentials
    assert "未加密的 MCP 认证凭据" in credentials
    assert "ensure_mcp_runtime_credential_access" in client
    assert "invalidate_session" in client
    assert "headers = decrypt_mcp_auth_headers(server.auth_headers)" in client
    assert "parse_mcp_auth_headers(data.auth_headers)" in endpoint
    assert "decrypt_mcp_auth_headers(data.auth_headers)" not in endpoint
    assert '"/credential-rotation"' in endpoint
    assert 'server_data["enabled_status"]' in endpoint
    assert 'server_data.get("enabled_status") or 1' not in endpoint
    assert '_ensure_server_runtime_ready(server, "同步工具")' in endpoint
    assert '_ensure_server_runtime_ready(server, "执行工具")' in endpoint
