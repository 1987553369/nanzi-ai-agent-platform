"""MCP authentication header encryption and validation helpers."""

import json
from typing import Dict, Optional

MCP_CREDENTIAL_PREFIX = "mcpheaders:v1:"


class McpCredentialError(ValueError):
    """Raised when MCP authentication headers are invalid or unreadable."""


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


def decrypt_mcp_auth_headers(stored_value: Optional[str]) -> Dict[str, str]:
    normalized = (stored_value or "").strip()
    if not normalized:
        return {}
    if normalized.startswith(MCP_CREDENTIAL_PREFIX):
        try:
            plaintext = get_api_key_manager().decrypt_api_key(
                normalized[len(MCP_CREDENTIAL_PREFIX):]
            )
        except ValueError as exc:
            raise McpCredentialError(
                "MCP 认证凭据无法解密，请检查 ENCRYPTION_KEY 或重新录入"
            ) from exc
        return parse_mcp_auth_headers(plaintext)

    # Backward compatibility for existing rows. New and updated rows are
    # always encrypted, so operators can migrate legacy rows without downtime.
    return parse_mcp_auth_headers(normalized)


def has_mcp_auth_headers(stored_value: Optional[str]) -> bool:
    normalized = (stored_value or "").strip()
    if not normalized:
        return False
    if normalized.startswith(MCP_CREDENTIAL_PREFIX):
        return True
    try:
        return bool(parse_mcp_auth_headers(normalized))
    except McpCredentialError:
        return True
