import asyncio
import socket

import pytest

from app.utils.outbound_url_policy import (
    OutboundUrlPolicyError,
    validate_outbound_http_url,
    validate_outbound_url,
    validate_resolved_addresses,
)


pytestmark = pytest.mark.no_infrastructure


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
    ],
)
def test_outbound_url_policy_rejects_unsafe_url_syntax(url):
    with pytest.raises(OutboundUrlPolicyError):
        validate_outbound_http_url(url)


def test_outbound_url_policy_normalizes_public_http_url():
    assert validate_outbound_http_url("HTTPS://Example.COM:443/mcp?x=1") == "https://example.com/mcp?x=1"


def test_outbound_url_policy_rejects_any_non_public_dns_answer():
    with pytest.raises(OutboundUrlPolicyError):
        validate_resolved_addresses(["93.184.216.34", "10.0.0.8"])


def test_outbound_url_policy_checks_dns_results(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert host == "public.example"
        assert port == 443
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(OutboundUrlPolicyError):
        asyncio.run(validate_outbound_url("https://public.example/mcp"))
