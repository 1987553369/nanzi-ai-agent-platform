"""Pure transformations for saved external database password migration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.utils.database_credentials import (
    DATABASE_CREDENTIAL_STATUS_EMPTY,
    DATABASE_CREDENTIAL_STATUS_ENCRYPTED,
    DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
    DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    DatabaseCredentialDecryptionError,
    decrypt_database_password,
    database_password_storage_status,
    encrypt_database_password,
)


@dataclass(frozen=True)
class DatabaseCredentialMigrationPlan:
    action: str
    stored_value: Optional[str]
    credential_status: str
    error_message: Optional[str] = None
    completed: bool = False


def plan_database_credential_migration(
    *,
    stored_value: Optional[str],
    recorded_status: Optional[str],
) -> DatabaseCredentialMigrationPlan:
    normalized_status = str(recorded_status or "").strip().lower()
    if normalized_status == DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED:
        return DatabaseCredentialMigrationPlan(
            action=DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
            stored_value=stored_value,
            credential_status=DATABASE_CREDENTIAL_STATUS_ROTATION_REQUIRED,
        )

    storage_status = database_password_storage_status(stored_value)
    try:
        if storage_status == DATABASE_CREDENTIAL_STATUS_EMPTY:
            return DatabaseCredentialMigrationPlan(
                action="empty",
                stored_value=None,
                credential_status=DATABASE_CREDENTIAL_STATUS_EMPTY,
                completed=True,
            )
        if storage_status == DATABASE_CREDENTIAL_STATUS_ENCRYPTED:
            decrypt_database_password(stored_value, DATABASE_CREDENTIAL_STATUS_ENCRYPTED)
            return DatabaseCredentialMigrationPlan(
                action="verified",
                stored_value=stored_value,
                credential_status=DATABASE_CREDENTIAL_STATUS_ENCRYPTED,
                completed=True,
            )
        encrypted = encrypt_database_password(stored_value)
        return DatabaseCredentialMigrationPlan(
            action="encrypted",
            stored_value=encrypted,
            credential_status=DATABASE_CREDENTIAL_STATUS_ENCRYPTED,
            completed=True,
        )
    except DatabaseCredentialDecryptionError:
        return DatabaseCredentialMigrationPlan(
            action=DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
            stored_value=stored_value,
            credential_status=DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
            error_message="版本化密文无法解密，请检查当前 ENCRYPTION_KEY 或重新录入",
        )
    except Exception as error:
        return DatabaseCredentialMigrationPlan(
            action=DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
            stored_value=stored_value,
            credential_status=DATABASE_CREDENTIAL_STATUS_MIGRATION_PENDING,
            error_message=f"凭据加密或校验失败：{type(error).__name__}",
        )


def migrate_database_credential_record(
    record: Any,
    *,
    apply: bool,
    migrated_at: Optional[datetime] = None,
) -> DatabaseCredentialMigrationPlan:
    plan = plan_database_credential_migration(
        stored_value=record.password,
        recorded_status=getattr(record, "password_status", None),
    )
    if not apply:
        return plan
    record.password = plan.stored_value
    record.password_status = plan.credential_status
    record.password_migration_error = (plan.error_message or "")[:500] or None
    record.password_migrated_at = (
        migrated_at or datetime.now() if plan.completed else None
    )
    return plan
