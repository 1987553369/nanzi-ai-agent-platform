"""Pure credential transformation used by the MCP migration command."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.utils.mcp_credentials import (
    MCP_CREDENTIAL_STATUS_EMPTY,
    MCP_CREDENTIAL_STATUS_ENCRYPTED,
    MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
    MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    McpCredentialDecryptionError,
    McpCredentialError,
    decrypt_mcp_auth_headers,
    encrypt_mcp_auth_headers,
    mcp_auth_headers_storage_status,
)


@dataclass(frozen=True)
class McpCredentialMigrationResult:
    action: str
    stored_value: Optional[str]
    credential_status: str


@dataclass(frozen=True)
class McpCredentialMigrationPlan:
    action: str
    stored_value: Optional[str]
    credential_status: str
    enabled_status: int
    restore_enabled_status: Optional[int]
    error_message: Optional[str] = None
    completed: bool = False


def _safe_migration_error(error: Exception) -> str:
    if isinstance(error, McpCredentialDecryptionError):
        return "版本化密文无法解密，请检查当前 ENCRYPTION_KEY；确认密钥正确后再重新录入"
    if isinstance(error, McpCredentialError):
        return "历史认证 Header 无法解析，请管理员重新录入"
    return f"凭据加密或校验失败：{type(error).__name__}"


def migrate_mcp_credential_value(
    stored_value: Optional[str],
) -> McpCredentialMigrationResult:
    """Encrypt legacy JSON, validate ciphertext, or normalize an empty value."""
    storage_status = mcp_auth_headers_storage_status(stored_value)
    if storage_status == MCP_CREDENTIAL_STATUS_EMPTY:
        return McpCredentialMigrationResult(
            action="empty",
            stored_value=None,
            credential_status=MCP_CREDENTIAL_STATUS_EMPTY,
        )
    if storage_status == MCP_CREDENTIAL_STATUS_ENCRYPTED:
        decrypt_mcp_auth_headers(stored_value)
        return McpCredentialMigrationResult(
            action="verified",
            stored_value=stored_value,
            credential_status=MCP_CREDENTIAL_STATUS_ENCRYPTED,
        )

    encrypted = encrypt_mcp_auth_headers(stored_value)
    return McpCredentialMigrationResult(
        action="encrypted" if encrypted else "empty",
        stored_value=encrypted,
        credential_status=(
            MCP_CREDENTIAL_STATUS_ENCRYPTED
            if encrypted
            else MCP_CREDENTIAL_STATUS_EMPTY
        ),
    )


def plan_mcp_credential_migration(
    *,
    stored_value: Optional[str],
    recorded_status: Optional[str],
    enabled_status: int,
    restore_enabled_status: Optional[int],
) -> McpCredentialMigrationPlan:
    """Plan one row transition without database access or side effects."""
    normalized_recorded_status = str(recorded_status or "").strip().lower()
    if normalized_recorded_status == MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED:
        return McpCredentialMigrationPlan(
            action=MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
            stored_value=stored_value,
            credential_status=MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
            enabled_status=0,
            restore_enabled_status=restore_enabled_status,
        )

    restore_status = (
        int(restore_enabled_status)
        if restore_enabled_status is not None
        else int(enabled_status or 0)
    )
    storage_status = mcp_auth_headers_storage_status(stored_value)
    try:
        migration = migrate_mcp_credential_value(stored_value)
    except McpCredentialDecryptionError as error:
        return McpCredentialMigrationPlan(
            action=MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
            stored_value=stored_value,
            credential_status=MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
            enabled_status=0,
            restore_enabled_status=restore_status,
            error_message=_safe_migration_error(error),
        )
    except McpCredentialError as error:
        return McpCredentialMigrationPlan(
            action=MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
            stored_value=(
                None
                if storage_status == MCP_CREDENTIAL_STATUS_MIGRATION_PENDING
                else stored_value
            ),
            credential_status=MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
            enabled_status=0,
            restore_enabled_status=restore_status,
            error_message=_safe_migration_error(error),
        )
    except Exception as error:
        return McpCredentialMigrationPlan(
            action=MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
            stored_value=stored_value,
            credential_status=MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
            enabled_status=0,
            restore_enabled_status=restore_status,
            error_message=_safe_migration_error(error),
        )

    return McpCredentialMigrationPlan(
        action=migration.action,
        stored_value=migration.stored_value,
        credential_status=migration.credential_status,
        enabled_status=restore_status,
        restore_enabled_status=None,
        completed=True,
    )


def migrate_mcp_credential_record(
    record: Any,
    *,
    apply: bool,
    migrated_at: Optional[datetime] = None,
) -> McpCredentialMigrationPlan:
    """Plan and optionally apply one migration without committing a session."""
    recorded_status = str(
        getattr(record, "auth_headers_status", None) or ""
    ).strip().lower()
    migration = plan_mcp_credential_migration(
        stored_value=record.auth_headers,
        recorded_status=recorded_status,
        enabled_status=int(record.enabled_status or 0),
        restore_enabled_status=getattr(
            record, "auth_headers_restore_enabled_status", None
        ),
    )
    if not apply:
        return migration
    if recorded_status == MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED:
        record.enabled_status = 0
        return migration

    record.auth_headers = migration.stored_value
    record.auth_headers_status = migration.credential_status
    record.auth_headers_restore_enabled_status = migration.restore_enabled_status
    record.auth_headers_migration_error = (migration.error_message or "")[:500] or None
    record.auth_headers_migrated_at = (
        migrated_at or datetime.now() if migration.completed else None
    )
    record.enabled_status = migration.enabled_status
    return migration
