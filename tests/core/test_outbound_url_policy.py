import asyncio
import socket
from pathlib import Path

import httpx
import pytest

from app.utils.outbound_url_policy import (
    OutboundUrlPolicyError,
    ResolvedIPTransport,
    create_private_network_access_policy,
    create_ssrf_safe_async_client,
    get_with_ssrf_safe_redirects,
    resolve_outbound_target,
    validate_outbound_http_url,
    validate_outbound_url,
    validate_resolved_addresses,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


def test_httpx_dependency_floor_covers_pinned_transport_contract():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "httpx>=0.27,<1" in requirements


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/service",
        "http://127.0.0.1/service",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/service",
        "http://user:pass@example.com/service",
        "https://example.com/service#fragment",
        "https://example.com:0/service",
        "https://127%2e0%2e0%2e1/service",
        "https://[fe80::1%25eth0]/service",
        "https://example.com\\@127.0.0.1/service",
        "https://example.com/line\nbreak",
    ],
)
def test_outbound_url_policy_rejects_unsafe_url_syntax(url):
    with pytest.raises(OutboundUrlPolicyError):
        validate_outbound_http_url(url)


def test_outbound_url_policy_normalizes_public_http_url():
    assert validate_outbound_http_url("HTTPS://Example.COM:443/mcp?x=1") == "https://example.com/mcp?x=1"


def test_outbound_url_policy_normalizes_idna_hostname():
    assert (
        validate_outbound_http_url("https://例子.测试/mcp")
        == "https://xn--fsqu00a.xn--0zwm56d/mcp"
    )


def test_outbound_url_policy_rejects_any_non_public_dns_answer():
    with pytest.raises(OutboundUrlPolicyError):
        validate_resolved_addresses(["93.184.216.34", "10.0.0.8"])


def test_private_policy_requires_both_exact_hosts_and_cidrs():
    with pytest.raises(OutboundUrlPolicyError, match="同时配置"):
        create_private_network_access_policy(["ragflow.internal"], [])
    with pytest.raises(OutboundUrlPolicyError, match="同时配置"):
        create_private_network_access_policy([], ["10.20.0.0/16"])


@pytest.mark.parametrize(
    "cidr",
    [
        "0.0.0.0/0",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::/0",
        "fe80::/10",
    ],
)
def test_private_policy_rejects_broad_or_special_networks(cidr):
    with pytest.raises(OutboundUrlPolicyError, match="RFC1918|ULA"):
        create_private_network_access_policy(["ragflow.internal"], [cidr])


def test_private_policy_rejects_wildcard_and_localhost_hosts():
    for host in ("*.internal", "localhost", "ragflow.localhost"):
        with pytest.raises(OutboundUrlPolicyError, match="Host"):
            create_private_network_access_policy([host], ["10.20.0.0/16"])


def test_private_policy_allows_exact_host_inside_approved_cidr(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert host == "ragflow.internal"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = create_private_network_access_policy(
        ["ragflow.internal"],
        ["10.20.0.0/16"],
    )

    target = asyncio.run(
        resolve_outbound_target(
            "http://ragflow.internal:9380/api/v1/datasets",
            private_network_policy=policy,
        )
    )

    assert target.connect_address == "10.20.1.8"
    assert target.hostname == "ragflow.internal"


def test_private_transport_pins_approved_target_and_retains_origin(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = create_private_network_access_policy(
        ["ragflow.internal", "other.internal"],
        ["10.20.0.0/16"],
    )
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(
        allowed_url="http://ragflow.internal:9380/api",
        private_network_policy=policy,
        transport=capture,
    )

    response = asyncio.run(
        transport.handle_async_request(
            httpx.Request(
                "POST",
                "http://ragflow.internal:9380/api/v1/retrieval",
                content=b"{}",
            )
        )
    )

    assert response.status_code == 200
    pinned = capture.requests[0]
    assert pinned.url.host == "10.20.1.8"
    assert pinned.headers["host"] == "ragflow.internal:9380"

    with pytest.raises(OutboundUrlPolicyError, match="跨 Origin"):
        asyncio.run(
            transport.handle_async_request(
                httpx.Request("GET", "http://other.internal:9380/api")
            )
        )


def test_private_policy_rejects_unapproved_host_before_network(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = create_private_network_access_policy(
        ["ragflow.internal"],
        ["10.20.0.0/16"],
    )

    with pytest.raises(OutboundUrlPolicyError, match="私网审批"):
        asyncio.run(
            resolve_outbound_target(
                "http://attacker.internal:9380/api",
                private_network_policy=policy,
            )
        )


def test_private_policy_rejects_address_outside_approved_cidr(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.30.1.8", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = create_private_network_access_policy(
        ["ragflow.internal"],
        ["10.20.0.0/16"],
    )

    with pytest.raises(OutboundUrlPolicyError, match="私网审批"):
        asyncio.run(
            resolve_outbound_target(
                "http://ragflow.internal:9380/api",
                private_network_policy=policy,
            )
        )


def test_private_policy_rejects_mixed_public_and_private_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = create_private_network_access_policy(
        ["ragflow.internal"],
        ["10.20.0.0/16"],
    )

    with pytest.raises(OutboundUrlPolicyError, match="同时解析"):
        asyncio.run(
            resolve_outbound_target(
                "http://ragflow.internal:9380/api",
                private_network_policy=policy,
            )
        )


def test_outbound_url_policy_checks_dns_results(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert host == "public.example"
        assert port == 443
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(OutboundUrlPolicyError):
        asyncio.run(validate_outbound_url("https://public.example/mcp"))


def test_resolved_target_validates_all_addresses_and_prefers_ipv4(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port, *, type):
        calls.append((host, port, type))
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    target = asyncio.run(resolve_outbound_target("https://PUBLIC.example:8443/mcp"))

    assert calls == [("public.example", 8443, socket.SOCK_STREAM)]
    assert target.url == "https://public.example:8443/mcp"
    assert target.addresses == ("2606:4700:4700::1111", "1.1.1.1")
    assert target.connect_address == "1.1.1.1"


def test_resolved_target_bounds_dns_resolution_time(monkeypatch):
    async def timeout(awaitable, *, timeout):
        awaitable.close()
        assert timeout == 5.0
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", timeout)

    with pytest.raises(OutboundUrlPolicyError, match="DNS 解析超时"):
        asyncio.run(resolve_outbound_target("https://slow.example/mcp"))


class _CaptureTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []
        self.closed = False

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async def aclose(self):
        self.closed = True


def test_transport_pins_socket_target_and_preserves_host_and_tls_sni(monkeypatch):
    dns_calls = 0

    def fake_getaddrinfo(host, port, *, type):
        nonlocal dns_calls
        dns_calls += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(transport=capture)
    request = httpx.Request(
        "POST",
        "https://service.example:8443/mcp?mode=sync",
        headers={"Authorization": "Bearer redacted"},
        content=b"{}",
    )

    response = asyncio.run(transport.handle_async_request(request))

    assert response.status_code == 200
    assert dns_calls == 1
    assert len(capture.requests) == 1
    pinned = capture.requests[0]
    assert str(pinned.url) == "https://93.184.216.34:8443/mcp?mode=sync"
    assert pinned.headers["host"] == "service.example:8443"
    assert pinned.headers["authorization"] == "Bearer redacted"
    assert pinned.extensions["sni_hostname"] == "service.example"


def test_transport_rejects_rebound_private_answer_before_network(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(transport=capture)

    with pytest.raises(OutboundUrlPolicyError, match="不是公网"):
        asyncio.run(
            transport.handle_async_request(
                httpx.Request("GET", "https://service.example/mcp")
            )
        )

    assert capture.requests == []


def test_transport_rejects_cross_origin_before_dns_or_network(monkeypatch):
    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("cross-origin requests must fail before DNS")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(
        allowed_url="https://service.example/mcp",
        transport=capture,
    )

    with pytest.raises(OutboundUrlPolicyError, match="跨 Origin"):
        asyncio.run(
            transport.handle_async_request(
                httpx.Request("POST", "https://attacker.example/messages")
            )
        )

    assert capture.requests == []


def test_transport_allows_same_origin_path_changes(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(
        allowed_url="https://service.example/mcp",
        transport=capture,
    )

    asyncio.run(
        transport.handle_async_request(
            httpx.Request("POST", "https://service.example/messages?session=1")
        )
    )

    assert len(capture.requests) == 1
    assert capture.requests[0].headers["host"] == "service.example"


def test_transport_skips_dns_for_valid_public_ip_literal(monkeypatch):
    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("public IP literals must not be resolved again")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)
    capture = _CaptureTransport()
    transport = ResolvedIPTransport(transport=capture)

    asyncio.run(
        transport.handle_async_request(
            httpx.Request("GET", "https://[2606:4700:4700::1111]/mcp")
        )
    )

    pinned = capture.requests[0]
    assert pinned.url.host == "2606:4700:4700::1111"
    assert pinned.headers["host"] == "[2606:4700:4700::1111]"


def test_ssrf_safe_client_cannot_enable_redirects_or_override_transport():
    with pytest.raises(ValueError, match="不允许自动重定向"):
        create_ssrf_safe_async_client(follow_redirects=True)
    with pytest.raises(ValueError, match="不允许覆盖"):
        create_ssrf_safe_async_client(transport=httpx.MockTransport(lambda request: None))
    with pytest.raises(ValueError, match="不允许关闭 TLS"):
        create_ssrf_safe_async_client(verify=False)
    with pytest.raises(ValueError, match="不允许调用方覆盖代理"):
        create_ssrf_safe_async_client(proxy="http://proxy.example")
    with pytest.raises(ValueError, match="不允许调用方覆盖代理"):
        create_ssrf_safe_async_client(proxies={"https://": "http://proxy.example"})
    with pytest.raises(ValueError, match="不允许旁路"):
        create_ssrf_safe_async_client(
            mounts={"https://": httpx.MockTransport(lambda request: None)}
        )
    private_policy = create_private_network_access_policy(
        ["ragflow.internal"],
        ["10.20.0.0/16"],
    )
    with pytest.raises(ValueError, match="绑定 allowed_url"):
        create_ssrf_safe_async_client(private_network_policy=private_policy)

    client = create_ssrf_safe_async_client(timeout=1.0)
    try:
        assert client.follow_redirects is False
        assert isinstance(client._transport, ResolvedIPTransport)
    finally:
        asyncio.run(client.aclose())


def test_real_transport_pools_are_isolated_by_original_hostname(monkeypatch):
    class _FakeRealTransport(_CaptureTransport):
        instances = []

        def __init__(self, **kwargs):
            super().__init__()
            self.kwargs = kwargs
            self.__class__.instances.append(self)

    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", _FakeRealTransport)
    transport = ResolvedIPTransport()

    async def execute():
        await transport.handle_async_request(httpx.Request("GET", "https://one.example/a"))
        await transport.handle_async_request(httpx.Request("GET", "https://two.example/b"))
        await transport.handle_async_request(httpx.Request("GET", "https://one.example/c"))
        await transport.aclose()

    asyncio.run(execute())

    assert len(_FakeRealTransport.instances) == 2
    assert [len(instance.requests) for instance in _FakeRealTransport.instances] == [2, 1]
    assert all(instance.closed for instance in _FakeRealTransport.instances)
    assert all(
        instance.kwargs == {"trust_env": False, "retries": 0}
        for instance in _FakeRealTransport.instances
    )


def test_transport_falls_back_across_prevalidated_addresses_only(monkeypatch):
    class _FallbackTransport(_CaptureTransport):
        instances = []

        def __init__(self, **kwargs):
            super().__init__()
            self.__class__.instances.append(self)

        async def handle_async_request(self, request):
            self.requests.append(request)
            if request.url.host == "93.184.216.34":
                raise httpx.ConnectError("primary unavailable", request=request)
            return httpx.Response(200, json={"ok": True})

    dns_calls = 0

    def fake_getaddrinfo(host, port, *, type):
        nonlocal dns_calls
        dns_calls += 1
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", _FallbackTransport)
    transport = ResolvedIPTransport()

    response = asyncio.run(
        transport.handle_async_request(
            httpx.Request("POST", "https://service.example/mcp", content=b"{}")
        )
    )

    assert response.status_code == 200
    assert dns_calls == 1
    assert len(_FallbackTransport.instances) == 2
    assert [
        instance.requests[0].url.host for instance in _FallbackTransport.instances
    ] == ["93.184.216.34", "93.184.216.35"]
    assert all(
        instance.requests[0].headers["host"] == "service.example"
        for instance in _FallbackTransport.instances
    )


def test_safe_redirects_reject_private_hop_before_second_request():
    class _RedirectClient:
        def __init__(self):
            self.calls = []
            self.responses = []

        async def get(self, url, headers=None):
            self.calls.append((url, headers))
            response = httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/admin"},
            )
            self.responses.append(response)
            return response

    client = _RedirectClient()
    with pytest.raises(OutboundUrlPolicyError, match="公网"):
        asyncio.run(
            get_with_ssrf_safe_redirects(
                client,
                "https://public.example/start",
            )
        )
    assert len(client.calls) == 1
    assert client.responses[0].is_closed


def test_safe_redirects_strip_credentials_when_origin_changes():
    class _RedirectClient:
        def __init__(self):
            self.calls = []

        async def get(self, url, headers=None):
            self.calls.append((url, dict(headers or {})))
            if len(self.calls) == 1:
                return httpx.Response(
                    302,
                    headers={"location": "https://cdn.example/final"},
                )
            return httpx.Response(200, text="ok")

    client = _RedirectClient()
    response = asyncio.run(
        get_with_ssrf_safe_redirects(
            client,
            "https://public.example/start",
            headers={
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "X-API-Key": "secret",
                "User-Agent": "NanZi-Test",
            },
        )
    )

    assert response.status_code == 200
    assert len(client.calls) == 2
    redirected_headers = client.calls[1][1]
    assert "Authorization" not in redirected_headers
    assert "Cookie" not in redirected_headers
    assert "X-API-Key" not in redirected_headers
    assert redirected_headers["User-Agent"] == "NanZi-Test"


def test_safe_redirects_enforce_hop_limit():
    class _RedirectClient:
        async def get(self, url, headers=None):
            return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(OutboundUrlPolicyError, match="次数过多"):
        asyncio.run(
            get_with_ssrf_safe_redirects(
                _RedirectClient(),
                "https://public.example/start",
                max_redirects=1,
            )
        )
