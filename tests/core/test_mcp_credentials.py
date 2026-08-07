import pytest

import app.utils.mcp_credentials as credentials


pytestmark = pytest.mark.no_infrastructure


class _FakeKeyManager:
    def encrypt_api_key(self, plaintext):
        return plaintext[::-1]

    def decrypt_api_key(self, encrypted):
        return encrypted[::-1]


def test_mcp_headers_are_encrypted_and_round_trip(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    stored = credentials.encrypt_mcp_auth_headers('{"Authorization":"Bearer secret"}')

    assert stored.startswith(credentials.MCP_CREDENTIAL_PREFIX)
    assert "secret" not in stored
    assert credentials.decrypt_mcp_auth_headers(stored) == {
        "Authorization": "Bearer secret"
    }
    assert credentials.has_mcp_auth_headers(stored) is True


def test_mcp_headers_reject_legacy_plaintext_at_runtime():
    with pytest.raises(credentials.McpCredentialError, match="未加密"):
        credentials.decrypt_mcp_auth_headers('{"X-API-Key":"legacy"}')


def test_mcp_header_storage_status_distinguishes_legacy_and_ciphertext():
    assert credentials.mcp_auth_headers_storage_status(None) == "empty"
    assert (
        credentials.mcp_auth_headers_storage_status('{"X-API-Key":"legacy"}')
        == "migration_pending"
    )
    assert (
        credentials.mcp_auth_headers_storage_status("mcpheaders:v1:ciphertext")
        == "encrypted"
    )
    assert (
        credentials.resolve_mcp_credential_status(
            "mcpheaders:v1:ciphertext", "rotation_required"
        )
        == "rotation_required"
    )


@pytest.mark.parametrize(
    ("enabled_status", "stored_value", "recorded_status", "expected"),
    [
        (1, None, "empty", "empty"),
        (1, "mcpheaders:v1:ciphertext", "encrypted", "encrypted"),
    ],
)
def test_mcp_runtime_access_allows_empty_or_encrypted_credentials(
    enabled_status,
    stored_value,
    recorded_status,
    expected,
):
    assert (
        credentials.ensure_mcp_runtime_credential_access(
            enabled_status=enabled_status,
            stored_value=stored_value,
            recorded_status=recorded_status,
        )
        == expected
    )


def test_mcp_runtime_access_rejects_disabled_service():
    with pytest.raises(credentials.McpCredentialError, match="已禁用"):
        credentials.ensure_mcp_runtime_credential_access(
            enabled_status=0,
            stored_value="mcpheaders:v1:ciphertext",
            recorded_status="encrypted",
        )


@pytest.mark.parametrize("status", ["migration_pending", "rotation_required"])
def test_mcp_runtime_access_rejects_quarantined_credentials(status):
    with pytest.raises(credentials.McpCredentialError, match="已隔离"):
        credentials.ensure_mcp_runtime_credential_access(
            enabled_status=1,
            stored_value="mcpheaders:v1:ciphertext",
            recorded_status=status,
        )


def test_mcp_runtime_access_rejects_unmarked_plaintext():
    with pytest.raises(credentials.McpCredentialError, match="已隔离"):
        credentials.ensure_mcp_runtime_credential_access(
            enabled_status=1,
            stored_value='{"Authorization":"legacy"}',
            recorded_status=None,
        )


@pytest.mark.parametrize(
    "value",
    [
        "[]",
        '{"Host":"internal"}',
        '{"Authorization":"Bearer value\\r\\nX-Evil: yes"}',
    ],
)
def test_mcp_headers_reject_invalid_or_dangerous_values(value):
    with pytest.raises(credentials.McpCredentialError):
        credentials.parse_mcp_auth_headers(value)
