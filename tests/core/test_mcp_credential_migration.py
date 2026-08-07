from pathlib import Path
from types import SimpleNamespace

import pytest

import app.utils.mcp_credentials as credentials
from app.services.mcp_credential_migration import (
    migrate_mcp_credential_record,
    migrate_mcp_credential_value,
    plan_mcp_credential_migration,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


class _FakeKeyManager:
    def encrypt_api_key(self, plaintext):
        return plaintext[::-1]

    def decrypt_api_key(self, encrypted):
        return encrypted[::-1]


def test_legacy_mcp_header_is_encrypted_and_round_trips(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    result = migrate_mcp_credential_value(
        '{"Authorization":"Bearer legacy-secret"}'
    )

    assert result.action == "encrypted"
    assert result.credential_status == "encrypted"
    assert result.stored_value.startswith(credentials.MCP_CREDENTIAL_PREFIX)
    assert "legacy-secret" not in result.stored_value
    assert credentials.decrypt_mcp_auth_headers(result.stored_value) == {
        "Authorization": "Bearer legacy-secret"
    }


def test_existing_ciphertext_must_be_decryptable(monkeypatch):
    class _BrokenKeyManager(_FakeKeyManager):
        def decrypt_api_key(self, encrypted):
            raise ValueError("bad ciphertext")

    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _BrokenKeyManager())

    with pytest.raises(credentials.McpCredentialDecryptionError, match="无法解密"):
        migrate_mcp_credential_value("mcpheaders:v1:corrupt")


def test_rotation_required_is_terminal_and_never_restores_service():
    plan = plan_mcp_credential_migration(
        stored_value=None,
        recorded_status="rotation_required",
        enabled_status=1,
        restore_enabled_status=1,
    )

    assert plan.action == "rotation_required"
    assert plan.credential_status == "rotation_required"
    assert plan.enabled_status == 0
    assert plan.restore_enabled_status == 1
    assert plan.completed is False


def test_rotation_required_apply_preserves_quarantine_details():
    server = SimpleNamespace(
        auth_headers=None,
        auth_headers_status="rotation_required",
        auth_headers_restore_enabled_status=1,
        auth_headers_migration_error="历史值无效",
        auth_headers_migrated_at=None,
        enabled_status=1,
    )
    before = dict(vars(server))

    migration = migrate_mcp_credential_record(server, apply=True)

    assert migration.action == "rotation_required"
    assert server.enabled_status == 0
    assert {
        key: value for key, value in vars(server).items() if key != "enabled_status"
    } == {
        key: value for key, value in before.items() if key != "enabled_status"
    }


def test_invalid_legacy_json_is_cleared_and_requires_rotation():
    plan = plan_mcp_credential_migration(
        stored_value="not-json",
        recorded_status="migration_pending",
        enabled_status=0,
        restore_enabled_status=1,
    )

    assert plan.action == "rotation_required"
    assert plan.stored_value is None
    assert plan.credential_status == "rotation_required"
    assert plan.enabled_status == 0
    assert plan.restore_enabled_status == 1
    assert "重新录入" in plan.error_message


def test_encryption_environment_failure_keeps_legacy_value_pending(monkeypatch):
    class _UnavailableKeyManager:
        def encrypt_api_key(self, plaintext):
            raise RuntimeError("key service unavailable")

    monkeypatch.setattr(
        credentials,
        "get_api_key_manager",
        lambda: _UnavailableKeyManager(),
    )

    legacy = '{"Authorization":"Bearer keep-me"}'
    plan = plan_mcp_credential_migration(
        stored_value=legacy,
        recorded_status="migration_pending",
        enabled_status=0,
        restore_enabled_status=1,
    )

    assert plan.action == "migration_pending"
    assert plan.stored_value == legacy
    assert plan.credential_status == "migration_pending"
    assert plan.enabled_status == 0
    assert plan.restore_enabled_status == 1
    assert "RuntimeError" in plan.error_message


def test_wrong_key_keeps_existing_ciphertext_pending(monkeypatch):
    class _WrongKeyManager:
        def decrypt_api_key(self, encrypted):
            raise ValueError("wrong key")

    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _WrongKeyManager())

    ciphertext = "mcpheaders:v1:existing"
    plan = plan_mcp_credential_migration(
        stored_value=ciphertext,
        recorded_status="encrypted",
        enabled_status=1,
        restore_enabled_status=None,
    )

    assert plan.action == "migration_pending"
    assert plan.stored_value == ciphertext
    assert plan.enabled_status == 0
    assert plan.restore_enabled_status == 1
    assert "ENCRYPTION_KEY" in plan.error_message


def test_successful_migration_restores_original_enabled_status(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    plan = plan_mcp_credential_migration(
        stored_value='{"Authorization":"Bearer legacy-secret"}',
        recorded_status="migration_pending",
        enabled_status=0,
        restore_enabled_status=1,
    )

    assert plan.action == "encrypted"
    assert plan.credential_status == "encrypted"
    assert plan.enabled_status == 1
    assert plan.restore_enabled_status is None
    assert plan.error_message is None
    assert plan.completed is True


def test_dry_run_does_not_commit_or_modify_server(monkeypatch):
    server = SimpleNamespace(
        auth_headers='{"Authorization":"Bearer legacy-secret"}',
        auth_headers_status="migration_pending",
        auth_headers_restore_enabled_status=1,
        auth_headers_migration_error="pending",
        auth_headers_migrated_at=None,
        enabled_status=0,
    )
    before = dict(vars(server))

    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    migration = migrate_mcp_credential_record(server, apply=False)

    assert migration.action == "encrypted"
    assert vars(server) == before


def test_apply_invalid_legacy_json_clears_and_disables_server(monkeypatch):
    server = SimpleNamespace(
        auth_headers="not-json",
        auth_headers_status="migration_pending",
        auth_headers_restore_enabled_status=1,
        auth_headers_migration_error=None,
        auth_headers_migrated_at=None,
        enabled_status=0,
    )
    migration = migrate_mcp_credential_record(server, apply=True)

    assert migration.action == "rotation_required"
    assert server.auth_headers is None
    assert server.auth_headers_status == "rotation_required"
    assert server.auth_headers_restore_enabled_status == 1
    assert server.auth_headers_migrated_at is None
    assert server.enabled_status == 0


def test_apply_success_encrypts_and_restores_server(monkeypatch):
    server = SimpleNamespace(
        auth_headers='{"Authorization":"Bearer legacy-secret"}',
        auth_headers_status="migration_pending",
        auth_headers_restore_enabled_status=1,
        auth_headers_migration_error="pending",
        auth_headers_migrated_at=None,
        enabled_status=0,
    )
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    migration = migrate_mcp_credential_record(server, apply=True)

    assert migration.action == "encrypted"
    assert server.auth_headers.startswith(credentials.MCP_CREDENTIAL_PREFIX)
    assert "legacy-secret" not in server.auth_headers
    assert server.auth_headers_status == "encrypted"
    assert server.auth_headers_restore_enabled_status is None
    assert server.auth_headers_migration_error is None
    assert server.auth_headers_migrated_at is not None
    assert server.enabled_status == 1


def test_migration_sql_quarantines_plaintext_without_embedding_secrets():
    mysql = (ROOT / "db-prod/V117-quarantine_legacy_mcp_credentials.sql").read_text(
        encoding="utf-8"
    )
    postgres = (
        ROOT / "db-prod-pg/V16-quarantine_legacy_mcp_credentials.sql"
    ).read_text(encoding="utf-8")

    for source in (mysql, postgres):
        assert "auth_headers_status" in source
        assert "auth_headers_restore_enabled_status" in source
        assert "migration_pending" in source
        assert "rotation_required" in source
        assert "mcpheaders:v1:%" in source
        assert "enabled_status" in source
        assert "Fernet" not in source
        assert "getenv" not in source
        assert "settings." not in source
        assert "不得保存明文 JSON" in source
        assert "ck_sys_mcp_servers_auth_headers_status" in source


def test_migration_command_defaults_to_dry_run_and_never_prints_header_values():
    source = (ROOT / "scripts/migrate_mcp_credentials.py").read_text(encoding="utf-8")

    assert 'apply = bool(args.apply)' in source
    assert 'mode = "APPLY" if apply else "DRY-RUN"' in source
    assert "print(server.auth_headers)" not in source
    assert "rotation_required" in source
    assert "with_for_update()" in source
    assert "migrate_mcp_credential_record" in source
