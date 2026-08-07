"""Shared outbound HTTP URL policy for SSRF-sensitive integrations."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable, Optional, Union
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

OUTBOUND_DNS_TIMEOUT_SECONDS = 5.0
OUTBOUND_MAX_REDIRECTS = 3
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_CROSS_ORIGIN_REDIRECT_HEADER_ALLOWLIST = {
    "accept",
    "accept-language",
    "range",
    "user-agent",
}
_APPROVABLE_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)

IpNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
IpAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


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


@dataclass(frozen=True)
class PrivateNetworkAccessPolicy:
    """Deployment-owned approval for one integration's exact private targets."""

    allowed_hosts: frozenset[str]
    allowed_networks: tuple[IpNetwork, ...]

    def allows(self, hostname: str, address: IpAddress) -> bool:
        return (
            _normalize_policy_hostname(hostname) in self.allowed_hosts
            and any(address in network for network in self.allowed_networks)
        )


def _effective_ip_address(address: str) -> IpAddress:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError as exc:
        raise OutboundUrlPolicyError("目标地址解析结果无效") from exc

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip


def _normalize_policy_hostname(hostname: str) -> str:
    normalized = str(hostname or "").strip().rstrip(".").lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if (
        not normalized
        or normalized == "localhost"
        or normalized.endswith(".localhost")
        or any(char in normalized for char in ("*", "/", "\\", "@", "?", "#"))
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise OutboundUrlPolicyError("私网审批 Host 格式无效")
    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        try:
            ascii_hostname = normalized.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise OutboundUrlPolicyError("私网审批 Host 的 IDNA 编码无效") from exc
        labels = ascii_hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not label.replace("-", "").isalnum()
            for label in labels
        ):
            raise OutboundUrlPolicyError("私网审批 Host 格式无效")
        return ascii_hostname


def create_private_network_access_policy(
    allowed_hosts: Iterable[str],
    allowed_cidrs: Iterable[str],
) -> Optional[PrivateNetworkAccessPolicy]:
    hosts = frozenset(
        _normalize_policy_hostname(hostname)
        for hostname in allowed_hosts
        if str(hostname or "").strip()
    )
    raw_cidrs = tuple(
        str(cidr or "").strip()
        for cidr in allowed_cidrs
        if str(cidr or "").strip()
    )
    if not hosts and not raw_cidrs:
        return None
    if not hosts or not raw_cidrs:
        raise OutboundUrlPolicyError("私网出网审批必须同时配置精确 Host 和 CIDR")

    networks: list[IpNetwork] = []
    for raw_cidr in raw_cidrs:
        try:
            network = ipaddress.ip_network(raw_cidr, strict=False)
        except ValueError as exc:
            raise OutboundUrlPolicyError(f"私网审批 CIDR 格式无效: {raw_cidr}") from exc
        if not any(
            network.version == private_range.version
            and network.subnet_of(private_range)
            for private_range in _APPROVABLE_PRIVATE_NETWORKS
        ):
            raise OutboundUrlPolicyError(
                "私网审批 CIDR 只允许 RFC1918 IPv4 或 IPv6 ULA 网段"
            )
        networks.append(network)

    for hostname in hosts:
        try:
            literal_ip = _effective_ip_address(hostname)
        except OutboundUrlPolicyError:
            continue
        if not any(literal_ip in network for network in networks):
            raise OutboundUrlPolicyError("私网审批中的 IP Host 不属于已批准 CIDR")

    return PrivateNetworkAccessPolicy(
        allowed_hosts=hosts,
        allowed_networks=tuple(networks),
    )


def _validate_ip_address(
    address: str,
    *,
    hostname: str = "",
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> bool:
    ip = _effective_ip_address(address)
    if not ip.is_global:
        if private_network_policy and private_network_policy.allows(hostname, ip):
            return True
        raise OutboundUrlPolicyError("目标地址不是公网地址或未通过私网审批")
    return False


def validate_outbound_http_url(
    url: str,
    *,
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> str:
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
        _validate_ip_address(
            hostname,
            hostname=hostname,
            private_network_policy=private_network_policy,
        )

    default_port = 443 if parsed.scheme.lower() == "https" else 80
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != default_port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def validate_resolved_addresses(
    addresses: Iterable[str],
    *,
    hostname: str = "",
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> None:
    resolved = list(dict.fromkeys(addresses))
    if not resolved:
        raise OutboundUrlPolicyError("目标主机没有可用 DNS 解析结果")
    private_results = {
        _validate_ip_address(
            address,
            hostname=hostname,
            private_network_policy=private_network_policy,
        )
        for address in resolved
    }
    if len(private_results) > 1:
        raise OutboundUrlPolicyError("目标主机不允许同时解析到公网和私网地址")


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


async def resolve_outbound_target(
    url: str,
    *,
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> ResolvedOutboundTarget:
    normalized = validate_outbound_http_url(
        url,
        private_network_policy=private_network_policy,
    )
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

    validate_resolved_addresses(
        addresses,
        hostname=hostname,
        private_network_policy=private_network_policy,
    )
    return ResolvedOutboundTarget(
        url=normalized,
        hostname=hostname,
        port=port,
        addresses=addresses,
        connect_address=_select_connect_address(addresses),
    )


async def validate_outbound_url(
    url: str,
    *,
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> str:
    return (
        await resolve_outbound_target(
            url,
            private_network_policy=private_network_policy,
        )
    ).url


def _original_host_header(target: ResolvedOutboundTarget, scheme: str) -> str:
    hostname = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
    default_port = 443 if scheme == "https" else 80
    return hostname if target.port == default_port else f"{hostname}:{target.port}"


def _outbound_authority(
    url: str,
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> tuple[str, str, int]:
    normalized = validate_outbound_http_url(
        url,
        private_network_policy=private_network_policy,
    )
    parsed = urlsplit(normalized)
    return (
        parsed.scheme,
        parsed.hostname or "",
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def outbound_url_origin(
    url: str,
    *,
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
) -> tuple[str, str, int]:
    """Return a normalized Origin tuple under the active outbound policy."""
    return _outbound_authority(url, private_network_policy)


def redact_outbound_url_for_log(url: str) -> str:
    """Keep only the target Origin; paths and queries may contain credentials."""
    try:
        parsed = urlsplit(str(url or "").strip())
        hostname = parsed.hostname or "invalid-host"
        host = f"[{hostname}]" if ":" in hostname else hostname
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, "", "", ""))
    except ValueError:
        return "invalid-url"


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
        private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if private_network_policy is not None and allowed_url is None:
            raise ValueError("私网出网策略必须绑定 allowed_url")
        self._allowed_authority = (
            _outbound_authority(allowed_url, private_network_policy)
            if allowed_url is not None
            else None
        )
        self._private_network_policy = private_network_policy
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
            and _outbound_authority(
                str(request.url),
                self._private_network_policy,
            ) != self._allowed_authority
        ):
            raise OutboundUrlPolicyError("后续请求不允许跨 Origin")
        target = await resolve_outbound_target(
            str(request.url),
            private_network_policy=self._private_network_policy,
        )
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
    private_network_policy: Optional[PrivateNetworkAccessPolicy] = None,
    **kwargs,
) -> httpx.AsyncClient:
    """Build an HTTP client that cannot re-resolve a verified host at connect time."""
    if private_network_policy is not None and allowed_url is None:
        raise ValueError("私网出网策略必须绑定 allowed_url")
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
    kwargs["transport"] = ResolvedIPTransport(
        allowed_url=allowed_url,
        private_network_policy=private_network_policy,
    )
    return httpx.AsyncClient(**kwargs)


async def get_with_ssrf_safe_redirects(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    max_redirects: int = OUTBOUND_MAX_REDIRECTS,
) -> httpx.Response:
    """Follow GET redirects explicitly, validating and pinning every hop."""
    if max_redirects < 0:
        raise ValueError("最大重定向次数不能为负数")

    current_url = validate_outbound_http_url(url)
    current_headers = dict(headers or {})
    for redirect_count in range(max_redirects + 1):
        response = await client.get(current_url, headers=current_headers)
        if response.status_code not in _REDIRECT_STATUS_CODES:
            return response

        location = response.headers.get("location")
        if not location:
            return response
        if redirect_count >= max_redirects:
            await response.aclose()
            raise OutboundUrlPolicyError("目标 URL 重定向次数过多")

        try:
            next_url = validate_outbound_http_url(urljoin(current_url, location))
        finally:
            await response.aclose()
        if _outbound_authority(next_url) != _outbound_authority(current_url):
            current_headers = {
                name: value
                for name, value in current_headers.items()
                if name.lower() in _CROSS_ORIGIN_REDIRECT_HEADER_ALLOWLIST
            }
        current_url = next_url

    raise OutboundUrlPolicyError("目标 URL 重定向次数过多")
