from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.utils.database_credentials as credentials
from app.services.database_credential_migration import (
    migrate_database_credential_record,
    plan_database_credential_migration,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


class _FakeKeyManager:
    def encrypt_api_key(self, plaintext):
        return plaintext[::-1]

    def decrypt_api_key(self, encrypted):
        return encrypted[::-1]


def _record(password="legacy-secret", status="migration_pending"):
    return SimpleNamespace(
        password=password,
        password_status=status,
        password_migration_error="pending",
        password_migrated_at=None,
    )


def test_legacy_password_migration_encrypts_and_round_trips(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    plan = plan_database_credential_migration(
        stored_value="legacy-secret",
        recorded_status="migration_pending",
    )

    assert plan.action == "encrypted"
    assert plan.credential_status == "encrypted"
    assert plan.stored_value.startswith(credentials.DATABASE_PASSWORD_PREFIX)
    assert "legacy-secret" not in plan.stored_value
    assert credentials.decrypt_database_password(plan.stored_value, "encrypted") == "legacy-secret"


def test_existing_ciphertext_is_verified(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    plan = plan_database_credential_migration(
        stored_value="dbpassword:v1:terces",
        recorded_status="encrypted",
    )

    assert plan.action == "verified"
    assert plan.completed is True
    assert plan.stored_value == "dbpassword:v1:terces"


def test_wrong_key_keeps_ciphertext_pending(monkeypatch):
    class _WrongKeyManager:
        def decrypt_api_key(self, encrypted):
            raise ValueError("wrong key")

    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _WrongKeyManager())
    ciphertext = "dbpassword:v1:existing"

    plan = plan_database_credential_migration(
        stored_value=ciphertext,
        recorded_status="encrypted",
    )

    assert plan.action == "migration_pending"
    assert plan.stored_value == ciphertext
    assert plan.credential_status == "migration_pending"
    assert "ENCRYPTION_KEY" in plan.error_message


def test_dry_run_does_not_modify_record(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())
    record = _record()
    before = dict(vars(record))

    plan = migrate_database_credential_record(record, apply=False)

    assert plan.action == "encrypted"
    assert vars(record) == before


def test_apply_updates_status_and_migration_time(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())
    record = _record()
    migrated_at = datetime(2026, 8, 7, 12, 0, 0)

    plan = migrate_database_credential_record(
        record,
        apply=True,
        migrated_at=migrated_at,
    )

    assert plan.action == "encrypted"
    assert record.password_status == "encrypted"
    assert record.password_migration_error is None
    assert record.password_migrated_at == migrated_at
    assert record.password.startswith(credentials.DATABASE_PASSWORD_PREFIX)


def test_migration_sql_only_quarantines_legacy_passwords():
    mysql = (ROOT / "db-prod/V118-quarantine_external_database_passwords.sql").read_text(encoding="utf-8")
    postgres = (ROOT / "db-prod-pg/V17-quarantine_external_database_passwords.sql").read_text(encoding="utf-8")

    for source in (mysql, postgres):
        assert "password_status" in source
        assert "migration_pending" in source
        assert "rotation_required" in source
        assert "dbpassword:v1:%" in source
        assert "CHECK" in source
        assert "Fernet" not in source
        assert "ENCRYPTION_KEY" not in source
        assert "Secret" not in source


def test_migration_command_defaults_to_dry_run_and_never_prints_passwords():
    source = (ROOT / "scripts/migrate_database_credentials.py").read_text(encoding="utf-8")

    assert "apply = bool(args.apply)" in source
    assert 'mode = "APPLY" if apply else "DRY-RUN"' in source
    assert "print(record.password)" not in source
    assert "print(config.password)" not in source
    assert "with_for_update()" in source
    assert "migrate_database_credential_record" in source
