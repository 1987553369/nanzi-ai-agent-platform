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


def test_mcp_client_redacts_credentials_and_disables_redirects():
    client = _source("app/services/ai/tools/mcp_client.py")

    assert "Auth Value" not in client
    assert "Sending Authorization" not in client
    assert "follow_redirects=True" not in client
    assert "follow_redirects=False" in client
    assert "validate_outbound_url" in client
    assert "httpx_client_factory" in client


def test_mcp_frontend_preserves_secret_without_server_echo():
    registry = _source("frontend/src/components/system/McpServerRegistry.vue")

    assert "server.auth_headers" not in registry
    assert "server.has_auth_headers" in registry
    assert "delete payload.auth_headers" in registry
    assert "authHeadersDirty" in registry
    assert "existingAuthHeadersConfigured.value && !authHeadersDirty.value" in registry
    assert 'type="password"' in registry
