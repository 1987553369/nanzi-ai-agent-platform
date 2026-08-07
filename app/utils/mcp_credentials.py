"""MCP authentication header encryption and validation helpers."""

import json
from typing import Dict, Optional

MCP_CREDENTIAL_PREFIX = "mcpheaders:v1:"
MCP_CREDENTIAL_STATUS_EMPTY = "empty"
MCP_CREDENTIAL_STATUS_ENCRYPTED = "encrypted"
MCP_CREDENTIAL_STATUS_MIGRATION_PENDING = "migration_pending"
MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED = "rotation_required"
MCP_CREDENTIAL_STATUSES = frozenset(
    {
        MCP_CREDENTIAL_STATUS_EMPTY,
        MCP_CREDENTIAL_STATUS_ENCRYPTED,
        MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
        MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }
)


class McpCredentialError(ValueError):
    """Raised when MCP authentication headers are invalid or unreadable."""


class McpCredentialDecryptionError(McpCredentialError):
    """Raised when versioned ciphertext cannot be decrypted in this environment."""


def get_api_key_manager():
    """Load the platform cipher lazily so pure validation has no settings dependency."""
    from app.utils.encryption import get_api_key_manager as factory

    return factory()


def parse_mcp_auth_headers(raw_value: Optional[str]) -> Dict[str, str]:
    normalized = (raw_value or "").strip()
    if not normalized:
        return {}
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise McpCredentialError("认证 Header 必须是合法 JSON 对象") from exc
    if not isinstance(value, dict):
        raise McpCredentialError("认证 Header 必须是 JSON 对象")

    headers: Dict[str, str] = {}
    blocked_names = {"host", "content-length", "transfer-encoding", "connection"}
    for key, value in value.items():
        header_name = str(key).strip()
        header_value = str(value)
        if not header_name or header_name.lower() in blocked_names:
            raise McpCredentialError(f"不允许设置 Header: {header_name or '(empty)'}")
        if "\r" in header_name or "\n" in header_name or "\r" in header_value or "\n" in header_value:
            raise McpCredentialError("认证 Header 不允许包含换行符")
        headers[header_name] = header_value
    return headers


def encrypt_mcp_auth_headers(raw_value: Optional[str]) -> Optional[str]:
    headers = parse_mcp_auth_headers(raw_value)
    if not headers:
        return None
    plaintext = json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
    encrypted = get_api_key_manager().encrypt_api_key(plaintext)
    return f"{MCP_CREDENTIAL_PREFIX}{encrypted}"


def mcp_auth_headers_storage_status(stored_value: Optional[str]) -> str:
    """Classify storage without parsing or exposing the credential payload."""
    normalized = (stored_value or "").strip()
    if not normalized:
        return MCP_CREDENTIAL_STATUS_EMPTY
    if normalized.startswith(MCP_CREDENTIAL_PREFIX):
        return MCP_CREDENTIAL_STATUS_ENCRYPTED
    return MCP_CREDENTIAL_STATUS_MIGRATION_PENDING


def resolve_mcp_credential_status(
    stored_value: Optional[str],
    recorded_status: Optional[str] = None,
) -> str:
    """Prefer an explicit quarantine state and otherwise verify storage shape."""
    normalized_status = str(recorded_status or "").strip().lower()
    if normalized_status in {
        MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
        MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }:
        return normalized_status
    return mcp_auth_headers_storage_status(stored_value)


def ensure_mcp_runtime_credential_access(
    *,
    enabled_status: object,
    stored_value: Optional[str],
    recorded_status: Optional[str] = None,
) -> str:
    """Reject disabled or quarantined services before credentials are decrypted."""
    if int(enabled_status or 0) != 1:
        raise McpCredentialError("MCP 服务已禁用")

    credential_status = resolve_mcp_credential_status(
        stored_value,
        recorded_status,
    )
    if credential_status in {
        MCP_CREDENTIAL_STATUS_MIGRATION_PENDING,
        MCP_CREDENTIAL_STATUS_ROTATION_REQUIRED,
    }:
        raise McpCredentialError("MCP 历史凭据已隔离，请完成迁移或重新录入")
    return credential_status


def decrypt_mcp_auth_headers(stored_value: Optional[str]) -> Dict[str, str]:
    normalized = (stored_value or "").strip()
    if not normalized:
        return {}
    if not normalized.startswith(MCP_CREDENTIAL_PREFIX):
        raise McpCredentialError(
            "检测到未加密的 MCP 认证凭据，运行时已拒绝读取；"
            "请先运行 scripts/migrate_mcp_credentials.py 或重新录入凭据"
        )
    try:
        plaintext = get_api_key_manager().decrypt_api_key(
            normalized[len(MCP_CREDENTIAL_PREFIX):]
        )
    except ValueError as exc:
        raise McpCredentialDecryptionError(
            "MCP 认证凭据无法解密，请检查 ENCRYPTION_KEY 或重新录入"
        ) from exc
    return parse_mcp_auth_headers(plaintext)


def has_mcp_auth_headers(stored_value: Optional[str]) -> bool:
    return bool((stored_value or "").strip())
