"""Versioned encryption helpers for saved external database passwords."""

from typing import Optional

DATABASE_PASSWORD_PREFIX = "dbpassword:v1:"
DATABASE_CREDENTIAL_STATUS_EMPTY = "empty"
DATABASE_CREDENTIAL_STATUS_ENCRYPTED = "encrypted"
DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING = "migration_pending"
DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED = "rotation_required"
DATABASE_CREDENTIAL_STATUSES = frozenset(
    {
        DATABASE_CREDENTIAL_STATUS_EMPTY,
        DATABASE_CREDENTIAL_STATUS_ENCRYPTED,
        DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
        DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }
)


class DatabaseCredentialError(ValueError):
    """Raised when a saved database password is unsafe or unreadable."""


class DatabaseCredentialDecryptionError(DatabaseCredentialError):
    """Raised when versioned ciphertext cannot be decrypted."""


def get_api_key_manager():
    from app.utils.encryption import get_api_key_manager as factory

    return factory()


def encrypt_database_password(password: Optional[str]) -> Optional[str]:
    if password is None or password == "":
        return None
    encrypted = get_api_key_manager().encrypt_api_key(str(password))
    return f"{DATABASE_PASSWORD_PREFIX}{encrypted}"


def database_password_storage_status(stored_value: Optional[str]) -> str:
    if stored_value is None or stored_value == "":
        return DATABASE_CREDENTIAL_STATUS_EMPTY
    if str(stored_value).startswith(DATABASE_PASSWORD_PREFIX):
        return DATABASE_CREDENTIAL_STATUS_ENCRYPTED
    return DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING


def resolve_database_credential_status(
    stored_value: Optional[str],
    recorded_status: Optional[str] = None,
) -> str:
    normalized_status = str(recorded_status or "").strip().lower()
    if normalized_status in {
        DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
        DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }:
        return normalized_status
    return database_password_storage_status(stored_value)


def decrypt_database_password(
    stored_value: Optional[str],
    recorded_status: Optional[str] = None,
) -> str:
    status = resolve_database_credential_status(stored_value, recorded_status)
    if status == DATABASE_CREDENTIAL_STATUS_EMPTY:
        return ""
    if status in {
        DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
        DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }:
        raise DatabaseCredentialError(
            "外部数据源历史密码已隔离，请完成迁移或重新录入"
        )
    normalized = str(stored_value or "")
    if not normalized.startswith(DATABASE_PASSWORD_PREFIX):
        raise DatabaseCredentialError("外部数据源密码不是受支持的版本化密文")
    try:
        return get_api_key_manager().decrypt_api_key(
            normalized[len(DATABASE_PASSWORD_PREFIX):]
        )
    except ValueError as exc:
        raise DatabaseCredentialDecryptionError(
            "外部数据源密码无法解密，请检查 ENCRYPTION_KEY 或重新录入"
        ) from exc


def has_database_password(stored_value: Optional[str]) -> bool:
    return stored_value is not None and stored_value != ""
