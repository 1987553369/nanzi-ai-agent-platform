import pytest

import app.utils.database_credentials as credentials


pytestmark = pytest.mark.no_infrastructure


class _FakeKeyManager:
    def encrypt_api_key(self, plaintext):
        return plaintext[::-1]

    def decrypt_api_key(self, encrypted):
        return encrypted[::-1]


def test_database_password_is_encrypted_and_round_trips(monkeypatch):
    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _FakeKeyManager())

    stored = credentials.encrypt_database_password("database-secret")

    assert stored.startswith(credentials.DATABASE_PASSWORD_PREFIX)
    assert "database-secret" not in stored
    assert credentials.decrypt_database_password(stored, "encrypted") == "database-secret"
    assert credentials.has_database_password(stored) is True


def test_empty_database_password_stays_empty():
    assert credentials.encrypt_database_password(None) is None
    assert credentials.encrypt_database_password("") is None
    assert credentials.decrypt_database_password(None, "empty") == ""
    assert credentials.has_database_password(None) is False


def test_database_password_storage_status_rejects_plaintext():
    assert credentials.database_password_storage_status(None) == "empty"
    assert credentials.database_password_storage_status("legacy-secret") == "migration_pending"
    assert credentials.database_password_storage_status("dbpassword:v1:ciphertext") == "encrypted"

    with pytest.raises(credentials.DatabaseCredentialError, match="历史密码已隔离"):
        credentials.decrypt_database_password("legacy-secret")


@pytest.mark.parametrize("status", ["migration_pending", "rotation_required"])
def test_quarantined_database_password_is_never_used(status):
    with pytest.raises(credentials.DatabaseCredentialError, match="历史密码已隔离"):
        credentials.decrypt_database_password("dbpassword:v1:ciphertext", status)


def test_wrong_encryption_key_never_falls_back_to_plaintext(monkeypatch):
    class _WrongKeyManager:
        def decrypt_api_key(self, encrypted):
            raise ValueError("wrong key")

    monkeypatch.setattr(credentials, "get_api_key_manager", lambda: _WrongKeyManager())

    with pytest.raises(credentials.DatabaseCredentialDecryptionError, match="无法解密"):
        credentials.decrypt_database_password("dbpassword:v1:ciphertext", "encrypted")
