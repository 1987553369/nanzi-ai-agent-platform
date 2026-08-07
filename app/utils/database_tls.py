"""外部数据库 TLS 策略和驱动参数构建器。"""

from __future__ import annotations

import re
import ssl
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


TLS_MODE_DISABLED = "disabled"
TLS_MODE_VERIFY_CA = "verify_ca"
TLS_MODE_VERIFY_IDENTITY = "verify_identity"
TLS_MODES = {
    TLS_MODE_DISABLED,
    TLS_MODE_VERIFY_CA,
    TLS_MODE_VERIFY_IDENTITY,
}

_TYPE_ALIASES = {
    "postgres": "postgresql",
    "pg": "postgresql",
    "mssql": "sqlserver",
    "tsql": "sqlserver",
}
_SUPPORTED_MODES = {
    "mysql": {TLS_MODE_DISABLED, TLS_MODE_VERIFY_CA},
    "clickhouse": {TLS_MODE_DISABLED, TLS_MODE_VERIFY_CA},
    "oracle": {TLS_MODE_DISABLED, TLS_MODE_VERIFY_CA},
    "postgresql": TLS_MODES,
    "sqlserver": {TLS_MODE_VERIFY_IDENTITY},
}


def normalize_database_type(db_type: Any) -> str:
    normalized = str(db_type or "").strip().lower()
    return _TYPE_ALIASES.get(normalized, normalized)


def normalize_tls_mode(db_type: Any, tls_mode: Any) -> str:
    normalized_type = normalize_database_type(db_type)
    value = str(tls_mode or "").strip().lower()
    if not value:
        return (
            TLS_MODE_VERIFY_IDENTITY
            if normalized_type == "sqlserver"
            else TLS_MODE_DISABLED
        )
    return value


def _runtime_policy() -> Tuple[bool, str]:
    from app.core.config import settings

    return bool(settings.DATA_SOURCE_REQUIRE_TLS), settings.DATA_SOURCE_TLS_CA_DIR


def validate_database_tls_config(
    db_type: Any,
    tls_mode: Any,
    tls_ca_path: Any = None,
    *,
    require_tls: Optional[bool] = None,
) -> Tuple[str, str]:
    normalized_type = normalize_database_type(db_type)
    if normalized_type not in _SUPPORTED_MODES:
        raise ValueError(f"不支持的数据库类型: {db_type}")

    mode = normalize_tls_mode(normalized_type, tls_mode)
    if mode not in TLS_MODES:
        raise ValueError("TLS 模式仅支持 disabled、verify_ca、verify_identity")
    if mode not in _SUPPORTED_MODES[normalized_type]:
        raise ValueError(f"{normalized_type} 不支持 TLS 模式 {mode}")

    if require_tls is None:
        require_tls, _ = _runtime_policy()
    if require_tls and mode == TLS_MODE_DISABLED:
        raise ValueError("当前部署强制数据源 TLS，禁止使用未加密连接")

    ca_path = str(tls_ca_path or "").strip()
    needs_ca = mode in {TLS_MODE_VERIFY_CA, TLS_MODE_VERIFY_IDENTITY} and normalized_type != "sqlserver"
    if needs_ca and not ca_path:
        raise ValueError("当前 TLS 模式必须配置 CA 相对路径")
    if mode == TLS_MODE_DISABLED and ca_path:
        raise ValueError("未启用 TLS 时不得配置 CA 路径")
    if normalized_type == "sqlserver" and ca_path:
        raise ValueError("SQL Server 使用系统信任库，不接受数据源级 CA 路径")
    if ca_path:
        relative = Path(ca_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("CA 路径必须是部署审批目录下的相对路径")
    return mode, ca_path


def resolve_database_tls_ca_path(
    tls_ca_path: str,
    *,
    ca_dir: Optional[str] = None,
    allow_directory: bool = False,
) -> str:
    relative = Path(str(tls_ca_path or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("CA 路径必须是部署审批目录下的相对路径")

    if ca_dir is None:
        _, ca_dir = _runtime_policy()
    ca_dir_value = str(ca_dir or "").strip()
    if not ca_dir_value:
        raise ValueError("未配置 DATA_SOURCE_TLS_CA_DIR")
    root = Path(ca_dir_value)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = (resolved_root / relative).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError("CA 路径不存在或超出部署审批目录") from exc

    if resolved.is_dir() and not allow_directory:
        raise ValueError("当前数据库驱动要求 CA 路径指向文件")
    if not resolved.is_file() and not (allow_directory and resolved.is_dir()):
        raise ValueError("CA 路径必须指向 CA 文件或受支持的证书目录")
    return str(resolved)


def _client_ssl_context(ca_path: str, *, verify_identity: bool = False) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = verify_identity
    path = Path(ca_path)
    if path.is_dir():
        context.load_verify_locations(capath=ca_path)
    else:
        context.load_verify_locations(cafile=ca_path)
    return context


def build_mysql_tls_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    mode, relative_ca = validate_database_tls_config(
        "mysql", config.get("tls_mode"), config.get("tls_ca_path")
    )
    if mode == TLS_MODE_DISABLED:
        return {}
    ca_path = resolve_database_tls_ca_path(relative_ca)
    return {"ssl": _client_ssl_context(ca_path)}


def build_clickhouse_tls_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    mode, relative_ca = validate_database_tls_config(
        "clickhouse", config.get("tls_mode"), config.get("tls_ca_path")
    )
    if mode == TLS_MODE_DISABLED:
        return {"secure": False}
    ca_path = resolve_database_tls_ca_path(relative_ca)
    return {"secure": True, "verify": True, "ca_certs": ca_path}


def build_postgresql_tls_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    mode, relative_ca = validate_database_tls_config(
        "postgresql", config.get("tls_mode"), config.get("tls_ca_path")
    )
    if mode == TLS_MODE_DISABLED:
        return {"sslmode": "disable"}
    ca_path = resolve_database_tls_ca_path(relative_ca)
    return {
        "sslmode": "verify-full" if mode == TLS_MODE_VERIFY_IDENTITY else "verify-ca",
        "sslrootcert": ca_path,
    }


def build_oracle_tls_connection(
    config: Dict[str, Any],
    *,
    connect_address: str,
    port: int,
    use_thick_mode: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    mode, relative_ca = validate_database_tls_config(
        "oracle", config.get("tls_mode"), config.get("tls_ca_path")
    )
    database = str(config.get("database") or config.get("database_name") or "").strip()
    service_name = str(config.get("service_name") or "").strip()
    oracle_identifier = service_name or database.lstrip("/")
    if not oracle_identifier or not re.fullmatch(r"[A-Za-z0-9_.-]+", oracle_identifier):
        raise ValueError("Oracle SID/Service Name 仅支持字母、数字、点、横线和下划线")
    connect_data = (
        f"(SERVICE_NAME={oracle_identifier})"
        if service_name or database.startswith("/")
        else f"(SID={oracle_identifier})"
    )
    protocol = "tcps" if mode == TLS_MODE_VERIFY_CA else "tcp"
    address = str(connect_address)
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    dsn = (
        f"(DESCRIPTION=(ADDRESS=(PROTOCOL={protocol})(HOST={address})(PORT={int(port)}))"
        f"(CONNECT_DATA={connect_data}))"
    )
    if mode == TLS_MODE_DISABLED:
        return dsn, {}
    ca_path = resolve_database_tls_ca_path(relative_ca, allow_directory=True)
    if Path(ca_path).is_dir():
        return dsn, {"config_dir": ca_path, "wallet_location": ca_path}
    if use_thick_mode:
        raise ValueError("Oracle Thick 模式要求 CA 路径指向 Wallet 配置目录")
    return dsn, {"ssl_context": _client_ssl_context(ca_path)}


def validate_sqlserver_tls(config: Dict[str, Any]) -> None:
    validate_database_tls_config(
        "sqlserver", config.get("tls_mode"), config.get("tls_ca_path")
    )
