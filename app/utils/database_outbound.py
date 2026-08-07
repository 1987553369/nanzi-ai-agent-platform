"""Outbound target policy for user-configured native database connections."""

import ipaddress
from dataclasses import dataclass
from typing import Iterable, Optional

from app.utils.outbound_url_policy import (
    OutboundUrlPolicyError,
    create_private_network_access_policy,
    resolve_outbound_target,
)


class DatabaseOutboundPolicyError(ValueError):
    """Raised when a database target violates deployment egress policy."""


@dataclass(frozen=True)
class ResolvedDatabaseTarget:
    hostname: str
    port: int
    addresses: tuple[str, ...]
    connect_address: str


def validate_database_allowed_ports(allowed_ports: Iterable[int]) -> tuple[int, ...]:
    ports: list[int] = []
    for raw_port in allowed_ports:
        if isinstance(raw_port, bool):
            raise DatabaseOutboundPolicyError("数据源端口审批格式无效")
        try:
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise DatabaseOutboundPolicyError("数据源端口审批格式无效") from exc
        if port < 1 or port > 65535:
            raise DatabaseOutboundPolicyError("数据源端口审批必须位于 1-65535")
        if port not in ports:
            ports.append(port)
    if not ports:
        raise DatabaseOutboundPolicyError("数据源端口审批不能为空")
    return tuple(ports)


def _database_target_url(hostname: str, port: int) -> str:
    raw_hostname = str(hostname or "").strip()
    if (
        not raw_hostname
        or any(char in raw_hostname for char in ("*", "/", "\\", "@", "?", "#", "%"))
        or any(ord(char) < 32 or ord(char) == 127 for char in raw_hostname)
    ):
        raise DatabaseOutboundPolicyError("数据源主机名格式无效")
    bracketed = raw_hostname.startswith("[") and raw_hostname.endswith("]")
    try:
        literal_ip = ipaddress.ip_address(
            raw_hostname[1:-1] if bracketed else raw_hostname
        )
    except ValueError:
        if ":" in raw_hostname or raw_hostname.startswith("[") or raw_hostname.endswith("]"):
            raise DatabaseOutboundPolicyError("数据源主机名格式无效")
        authority = raw_hostname
    else:
        authority = f"[{literal_ip}]" if literal_ip.version == 6 else str(literal_ip)
    return f"http://{authority}:{port}/"


async def resolve_database_target(
    hostname: str,
    port: int,
    *,
    allowed_private_hosts: Optional[Iterable[str]] = None,
    allowed_private_cidrs: Optional[Iterable[str]] = None,
    allowed_ports: Optional[Iterable[int]] = None,
) -> ResolvedDatabaseTarget:
    """Resolve and validate a database host once before a driver connects."""
    if (
        allowed_private_hosts is None
        or allowed_private_cidrs is None
        or allowed_ports is None
    ):
        from app.core.config import settings

        if allowed_private_hosts is None:
            allowed_private_hosts = settings.DATA_SOURCE_ALLOWED_PRIVATE_HOSTS
        if allowed_private_cidrs is None:
            allowed_private_cidrs = settings.DATA_SOURCE_ALLOWED_PRIVATE_CIDRS
        if allowed_ports is None:
            allowed_ports = settings.DATA_SOURCE_ALLOWED_PORTS

    approved_ports = validate_database_allowed_ports(allowed_ports)
    try:
        target_port = int(port)
    except (TypeError, ValueError) as exc:
        raise DatabaseOutboundPolicyError("数据源端口格式无效") from exc
    if target_port not in approved_ports:
        raise DatabaseOutboundPolicyError("数据源端口未通过部署审批")

    try:
        private_policy = create_private_network_access_policy(
            allowed_private_hosts,
            allowed_private_cidrs,
        )
        target = await resolve_outbound_target(
            _database_target_url(hostname, target_port),
            private_network_policy=private_policy,
        )
    except OutboundUrlPolicyError as exc:
        raise DatabaseOutboundPolicyError(str(exc)) from exc
    return ResolvedDatabaseTarget(
        hostname=target.hostname,
        port=target.port,
        addresses=target.addresses,
        connect_address=target.connect_address,
    )
