"""Shared outbound HTTP URL policy for SSRF-sensitive integrations."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

OUTBOUND_DNS_TIMEOUT_SECONDS = 5.0


class OutboundUrlPolicyError(ValueError):
    """Raised when an outbound URL is unsafe or cannot be verified."""


@dataclass(frozen=True)
class ResolvedOutboundTarget:
    """One normalized URL and the public addresses approved for its next connect."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]
    connect_address: str


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
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise OutboundUrlPolicyError("目标 URL 不允许包含控制字符")
    if "\\" in normalized:
        raise OutboundUrlPolicyError("目标 URL 不允许包含反斜杠")
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
    if port == 0:
        raise OutboundUrlPolicyError("目标 URL 端口无效")

    hostname = parsed.hostname.rstrip(".").lower()
    if "%" in hostname:
        raise OutboundUrlPolicyError("目标主机名不允许使用百分号编码或 Zone ID")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise OutboundUrlPolicyError("目标 URL 不允许访问本机")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise OutboundUrlPolicyError("目标主机名 IDNA 编码无效") from exc
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


def _deduplicate_addresses(addresses: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(address.split("%", 1)[0] for address in addresses))


def _select_connect_address(addresses: tuple[str, ...]) -> str:
    """Prefer IPv4 where both families exist to avoid IPv6-only routing failures."""
    return _ordered_connect_addresses(addresses)[0]


def _ordered_connect_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(
        addresses,
        key=lambda address: (
            isinstance(ipaddress.ip_address(address), ipaddress.IPv6Address),
            addresses.index(address),
        ),
    ))


async def resolve_outbound_target(url: str) -> ResolvedOutboundTarget:
    normalized = validate_outbound_http_url(url)
    parsed = urlsplit(normalized)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    hostname = parsed.hostname or ""
    try:
        literal_ip = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        try:
            records = await asyncio.wait_for(
                asyncio.to_thread(
                    socket.getaddrinfo,
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                ),
                timeout=OUTBOUND_DNS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise OutboundUrlPolicyError("目标主机 DNS 解析超时") from exc
        except socket.gaierror as exc:
            raise OutboundUrlPolicyError("目标主机 DNS 解析失败") from exc
        addresses = _deduplicate_addresses(record[4][0] for record in records)
    else:
        addresses = (str(literal_ip),)

    validate_resolved_addresses(addresses)
    return ResolvedOutboundTarget(
        url=normalized,
        hostname=hostname,
        port=port,
        addresses=addresses,
        connect_address=_select_connect_address(addresses),
    )


async def validate_outbound_url(url: str) -> str:
    return (await resolve_outbound_target(url)).url


def _original_host_header(target: ResolvedOutboundTarget, scheme: str) -> str:
    hostname = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
    default_port = 443 if scheme == "https" else 80
    return hostname if target.port == default_port else f"{hostname}:{target.port}"


def _outbound_authority(url: str) -> tuple[str, str, int]:
    normalized = validate_outbound_http_url(url)
    parsed = urlsplit(normalized)
    return (
        parsed.scheme,
        parsed.hostname or "",
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def pin_outbound_request(
    request: httpx.Request,
    target: ResolvedOutboundTarget,
    *,
    connect_address: Optional[str] = None,
) -> httpx.Request:
    """Replace only the socket destination while retaining HTTP/TLS authority."""
    headers = request.headers.copy()
    headers["Host"] = _original_host_header(target, request.url.scheme)
    extensions = dict(request.extensions)
    if request.url.scheme == "https":
        extensions["sni_hostname"] = target.hostname
    return httpx.Request(
        method=request.method,
        url=request.url.copy_with(host=connect_address or target.connect_address),
        headers=headers,
        stream=request.stream,
        extensions=extensions,
    )


class ResolvedIPTransport(httpx.AsyncBaseTransport):
    """Resolve, validate and pin every outbound request before opening a socket."""

    def __init__(
        self,
        *,
        allowed_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._allowed_authority = (
            _outbound_authority(allowed_url) if allowed_url is not None else None
        )
        self._test_transport = transport
        self._transports: dict[
            tuple[str, str, int, str],
            httpx.AsyncBaseTransport,
        ] = {}
        self._transport_lock: Optional[asyncio.Lock] = None

    async def _transport_for(
        self,
        request: httpx.Request,
        target: ResolvedOutboundTarget,
        connect_address: str,
    ) -> httpx.AsyncBaseTransport:
        if self._test_transport is not None:
            return self._test_transport
        key = (
            request.url.scheme,
            target.hostname,
            target.port,
            connect_address,
        )
        if self._transport_lock is None:
            self._transport_lock = asyncio.Lock()
        async with self._transport_lock:
            transport = self._transports.get(key)
            if transport is None:
                transport = httpx.AsyncHTTPTransport(
                    trust_env=False,
                    retries=0,
                )
                self._transports[key] = transport
            return transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (
            self._allowed_authority is not None
            and _outbound_authority(str(request.url)) != self._allowed_authority
        ):
            raise OutboundUrlPolicyError("MCP 后续请求不允许跨 Origin")
        target = await resolve_outbound_target(str(request.url))
        last_connect_error: Optional[Exception] = None
        for connect_address in _ordered_connect_addresses(target.addresses):
            transport = await self._transport_for(
                request,
                target,
                connect_address,
            )
            try:
                return await transport.handle_async_request(
                    pin_outbound_request(
                        request,
                        target,
                        connect_address=connect_address,
                    )
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_connect_error = exc
        assert last_connect_error is not None
        raise last_connect_error

    async def aclose(self) -> None:
        transports = list(self._transports.values())
        if self._test_transport is not None:
            transports.append(self._test_transport)
        self._transports.clear()
        for transport in transports:
            await transport.aclose()


def create_ssrf_safe_async_client(
    *,
    allowed_url: Optional[str] = None,
    **kwargs,
) -> httpx.AsyncClient:
    """Build an HTTP client that cannot re-resolve a verified host at connect time."""
    if kwargs.get("follow_redirects"):
        raise ValueError("SSRF 安全客户端不允许自动重定向")
    if kwargs.get("transport") is not None:
        raise ValueError("SSRF 安全客户端不允许覆盖固定解析 Transport")
    if kwargs.get("verify") is False:
        raise ValueError("SSRF 安全客户端不允许关闭 TLS 证书校验")
    if kwargs.get("proxy") is not None:
        raise ValueError("SSRF 安全客户端不允许调用方覆盖代理")
    if kwargs.get("proxies") is not None:
        raise ValueError("SSRF 安全客户端不允许调用方覆盖代理")
    if kwargs.get("mounts") is not None or kwargs.get("app") is not None:
        raise ValueError("SSRF 安全客户端不允许旁路固定解析 Transport")
    kwargs["follow_redirects"] = False
    kwargs["trust_env"] = False
    kwargs["transport"] = ResolvedIPTransport(allowed_url=allowed_url)
    return httpx.AsyncClient(**kwargs)
