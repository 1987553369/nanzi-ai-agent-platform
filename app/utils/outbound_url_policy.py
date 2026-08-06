"""Shared outbound HTTP URL policy for SSRF-sensitive integrations."""

import asyncio
import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit


class OutboundUrlPolicyError(ValueError):
    """Raised when an outbound URL is unsafe or cannot be verified."""


def _validate_ip_address(address: str) -> None:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError as exc:
        raise OutboundUrlPolicyError("目标地址解析结果无效") from exc

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global:
        raise OutboundUrlPolicyError("目标地址不是公网地址")


def validate_outbound_http_url(url: str) -> str:
    normalized = str(url or "").strip()
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise OutboundUrlPolicyError("目标 URL 格式无效") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise OutboundUrlPolicyError("目标 URL 只允许 http 或 https")
    if not parsed.hostname:
        raise OutboundUrlPolicyError("目标 URL 缺少主机名")
    if parsed.username is not None or parsed.password is not None:
        raise OutboundUrlPolicyError("目标 URL 不允许包含用户名或密码")
    if parsed.fragment:
        raise OutboundUrlPolicyError("目标 URL 不允许包含 fragment")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise OutboundUrlPolicyError("目标 URL 不允许访问本机")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _validate_ip_address(hostname)

    default_port = 443 if parsed.scheme.lower() == "https" else 80
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != default_port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def validate_resolved_addresses(addresses: Iterable[str]) -> None:
    resolved = list(dict.fromkeys(addresses))
    if not resolved:
        raise OutboundUrlPolicyError("目标主机没有可用 DNS 解析结果")
    for address in resolved:
        _validate_ip_address(address)


async def validate_outbound_url(url: str) -> str:
    normalized = validate_outbound_http_url(url)
    parsed = urlsplit(normalized)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise OutboundUrlPolicyError("目标主机 DNS 解析失败") from exc
    validate_resolved_addresses(record[4][0] for record in records)
    return normalized
