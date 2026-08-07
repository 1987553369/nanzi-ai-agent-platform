"""SMTP outbound policy with DNS pinning and mandatory TLS."""

import asyncio
import ipaddress
import smtplib
import socket
import ssl
from dataclasses import dataclass
from typing import Iterable, Optional

from app.utils.outbound_url_policy import (
    OUTBOUND_DNS_TIMEOUT_SECONDS,
    OutboundUrlPolicyError,
    create_private_network_access_policy,
    validate_resolved_addresses,
)


class SmtpPolicyError(ValueError):
    """Raised when an SMTP target violates the deployment egress policy."""


@dataclass(frozen=True)
class ResolvedSmtpTarget:
    hostname: str
    port: int
    addresses: tuple[str, ...]


def validate_smtp_allowed_ports(allowed_ports: Iterable[int]) -> tuple[int, ...]:
    ports: list[int] = []
    for raw_port in allowed_ports:
        if isinstance(raw_port, bool):
            raise SmtpPolicyError("SMTP 端口审批格式无效")
        try:
            port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise SmtpPolicyError("SMTP 端口审批格式无效") from exc
        if port < 1 or port > 65535:
            raise SmtpPolicyError("SMTP 端口审批必须位于 1-65535")
        if port not in ports:
            ports.append(port)
    if not ports:
        raise SmtpPolicyError("SMTP 端口审批不能为空")
    return tuple(ports)


def _normalize_smtp_hostname(hostname: str) -> str:
    normalized = str(hostname or "").strip().rstrip(".").lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if (
        not normalized
        or normalized == "localhost"
        or normalized.endswith(".localhost")
        or any(char in normalized for char in ("*", "/", "\\", "@", "?", "#", "%"))
        or "://" in normalized
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise SmtpPolicyError("SMTP 主机名格式无效")

    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        try:
            ascii_hostname = normalized.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise SmtpPolicyError("SMTP 主机名 IDNA 编码无效") from exc
        labels = ascii_hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not label.replace("-", "").isalnum()
            for label in labels
        ):
            raise SmtpPolicyError("SMTP 主机名格式无效")
        return ascii_hostname


def _deduplicate_addresses(addresses: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(address.split("%", 1)[0] for address in addresses))


def _ordered_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            addresses,
            key=lambda address: (
                isinstance(ipaddress.ip_address(address), ipaddress.IPv6Address),
                addresses.index(address),
            ),
        )
    )


async def resolve_smtp_target(
    hostname: str,
    port: int,
    *,
    allowed_private_hosts: Optional[Iterable[str]] = None,
    allowed_private_cidrs: Optional[Iterable[str]] = None,
    allowed_ports: Optional[Iterable[int]] = None,
) -> ResolvedSmtpTarget:
    """Resolve every SMTP address once, validate it, then return pinned targets."""
    if (
        allowed_private_hosts is None
        or allowed_private_cidrs is None
        or allowed_ports is None
    ):
        from app.core.config import settings

        if allowed_private_hosts is None:
            allowed_private_hosts = settings.SMTP_ALLOWED_PRIVATE_HOSTS
        if allowed_private_cidrs is None:
            allowed_private_cidrs = settings.SMTP_ALLOWED_PRIVATE_CIDRS
        if allowed_ports is None:
            allowed_ports = settings.SMTP_ALLOWED_PORTS

    approved_ports = validate_smtp_allowed_ports(allowed_ports)
    try:
        target_port = int(port)
    except (TypeError, ValueError) as exc:
        raise SmtpPolicyError("SMTP 端口格式无效") from exc
    if target_port not in approved_ports:
        raise SmtpPolicyError("SMTP 端口未通过部署审批")

    target_hostname = _normalize_smtp_hostname(hostname)
    try:
        private_policy = create_private_network_access_policy(
            allowed_private_hosts,
            allowed_private_cidrs,
        )
    except OutboundUrlPolicyError as exc:
        raise SmtpPolicyError(str(exc)) from exc

    try:
        literal_ip = ipaddress.ip_address(target_hostname)
    except ValueError:
        try:
            records = await asyncio.wait_for(
                asyncio.to_thread(
                    socket.getaddrinfo,
                    target_hostname,
                    target_port,
                    type=socket.SOCK_STREAM,
                ),
                timeout=OUTBOUND_DNS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise SmtpPolicyError("SMTP 主机 DNS 解析超时") from exc
        except socket.gaierror as exc:
            raise SmtpPolicyError("SMTP 主机 DNS 解析失败") from exc
        addresses = _deduplicate_addresses(record[4][0] for record in records)
    else:
        addresses = (str(literal_ip),)

    try:
        validate_resolved_addresses(
            addresses,
            hostname=target_hostname,
            private_network_policy=private_policy,
        )
    except OutboundUrlPolicyError as exc:
        raise SmtpPolicyError(str(exc)) from exc
    return ResolvedSmtpTarget(
        hostname=target_hostname,
        port=target_port,
        addresses=_ordered_addresses(addresses),
    )


class _PinnedSMTP(smtplib.SMTP):
    def __init__(self, hostname: str, connect_address: str, port: int, timeout: float):
        self._connect_address = connect_address
        super().__init__(hostname, port, timeout=timeout)

    def _get_socket(self, host: str, port: int, timeout: float):
        return socket.create_connection(
            (self._connect_address, port),
            timeout,
            self.source_address,
        )


class _PinnedSMTP_SSL(smtplib.SMTP_SSL):
    def __init__(
        self,
        hostname: str,
        connect_address: str,
        port: int,
        timeout: float,
        context: ssl.SSLContext,
    ):
        self._connect_address = connect_address
        super().__init__(hostname, port, timeout=timeout, context=context)

    def _get_socket(self, host: str, port: int, timeout: float):
        raw_socket = socket.create_connection(
            (self._connect_address, port),
            timeout,
            self.source_address,
        )
        try:
            return self.context.wrap_socket(raw_socket, server_hostname=self._host)
        except Exception:
            raw_socket.close()
            raise


def _open_smtp_connection(
    target: ResolvedSmtpTarget,
    *,
    timeout: float,
    context: ssl.SSLContext,
) -> smtplib.SMTP:
    last_error: Optional[Exception] = None
    for address in target.addresses:
        try:
            if target.port == 465:
                return _PinnedSMTP_SSL(
                    target.hostname,
                    address,
                    target.port,
                    timeout,
                    context,
                )
            return _PinnedSMTP(
                target.hostname,
                address,
                target.port,
                timeout,
            )
        except ssl.SSLError:
            raise
        except (OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
            last_error = exc
    if last_error is None:
        raise SmtpPolicyError("SMTP 主机没有可用地址")
    raise last_error


def _send_resolved_smtp_message(
    target: ResolvedSmtpTarget,
    *,
    username: str,
    password: str,
    recipient: str,
    message: str,
    timeout: float,
) -> None:
    context = ssl.create_default_context()
    server = _open_smtp_connection(target, timeout=timeout, context=context)
    try:
        if target.port != 465:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        server.login(username, password)
        server.sendmail(username, [recipient], message)
    finally:
        server.close()


async def send_smtp_message(
    *,
    hostname: str,
    port: int,
    username: str,
    password: str,
    recipient: str,
    message: str,
    timeout: float = 10.0,
) -> None:
    """Send one message after policy validation; never retry after authentication."""
    target = await resolve_smtp_target(hostname, port)
    await asyncio.to_thread(
        _send_resolved_smtp_message,
        target,
        username=username,
        password=password,
        recipient=recipient,
        message=message,
        timeout=timeout,
    )
