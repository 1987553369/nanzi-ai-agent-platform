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


def test_mcp_headers_support_legacy_plaintext_during_migration():
    assert credentials.decrypt_mcp_auth_headers('{"X-API-Key":"legacy"}') == {
        "X-API-Key": "legacy"
    }


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
