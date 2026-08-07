import asyncio
import smtplib
import socket
import ssl
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.utils import smtp_policy
from app.utils.smtp_policy import (
    ResolvedSmtpTarget,
    SmtpPolicyError,
    _PinnedSMTP,
    _PinnedSMTP_SSL,
    _send_resolved_smtp_message,
    resolve_smtp_target,
    validate_smtp_allowed_ports,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


def _resolve(hostname, port=587, **overrides):
    options = {
        "allowed_private_hosts": [],
        "allowed_private_cidrs": [],
        "allowed_ports": [465, 587],
    }
    options.update(overrides)
    return asyncio.run(resolve_smtp_target(hostname, port, **options))


def test_smtp_resolver_validates_all_results_and_prefers_ipv4(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert (host, port, type) == ("smtp.example", 587, socket.SOCK_STREAM)
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    target = _resolve("SMTP.Example.")

    assert target.hostname == "smtp.example"
    assert target.addresses == ("1.1.1.1", "2606:4700:4700::1111")


def test_smtp_private_target_requires_exact_host_and_cidr(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port))
        ],
    )

    with pytest.raises(SmtpPolicyError, match="私网审批"):
        _resolve("smtp.internal")
    with pytest.raises(SmtpPolicyError, match="私网审批"):
        _resolve(
            "other.internal",
            allowed_private_hosts=["smtp.internal"],
            allowed_private_cidrs=["10.20.1.0/24"],
        )

    target = _resolve(
        "smtp.internal",
        allowed_private_hosts=["smtp.internal"],
        allowed_private_cidrs=["10.20.1.0/24"],
    )
    assert target.addresses == ("10.20.1.8",)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "169.254.169.254", "::1", "fe80::1"],
)
def test_smtp_rejects_loopback_and_link_local_addresses(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 587, 0, 0) if family == socket.AF_INET6 else (address, 587)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [(family, socket.SOCK_STREAM, 6, "", sockaddr)],
    )

    with pytest.raises(SmtpPolicyError, match="公网地址|私网审批"):
        _resolve("smtp.example")


def test_smtp_rejects_mixed_public_and_private_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port)),
        ],
    )

    with pytest.raises(SmtpPolicyError):
        _resolve(
            "smtp.internal",
            allowed_private_hosts=["smtp.internal"],
            allowed_private_cidrs=["10.20.1.0/24"],
        )


def test_smtp_rejects_unapproved_port_before_dns(monkeypatch):
    resolver = MagicMock()
    monkeypatch.setattr(socket, "getaddrinfo", resolver)

    with pytest.raises(SmtpPolicyError, match="端口未通过部署审批"):
        _resolve("smtp.example", 25)
    resolver.assert_not_called()


def test_smtp_port_policy_rejects_boolean_values():
    with pytest.raises(SmtpPolicyError, match="端口审批格式无效"):
        validate_smtp_allowed_ports([True])


def test_pinned_smtp_socket_connects_to_approved_ip(monkeypatch):
    marker = object()
    create_connection = MagicMock(return_value=marker)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    client = object.__new__(_PinnedSMTP)
    client._connect_address = "1.1.1.1"
    client.source_address = None

    result = client._get_socket("smtp.example", 587, 10.0)

    assert result is marker
    create_connection.assert_called_once_with(("1.1.1.1", 587), 10.0, None)


def test_pinned_smtp_ssl_connects_to_ip_but_verifies_original_hostname(monkeypatch):
    raw_socket = MagicMock()
    wrapped_socket = object()
    context = MagicMock()
    context.wrap_socket.return_value = wrapped_socket
    monkeypatch.setattr(socket, "create_connection", MagicMock(return_value=raw_socket))
    client = object.__new__(_PinnedSMTP_SSL)
    client._connect_address = "1.1.1.1"
    client.source_address = None
    client.context = context
    client._host = "smtp.example"

    result = client._get_socket("smtp.example", 465, 10.0)

    assert result is wrapped_socket
    context.wrap_socket.assert_called_once_with(
        raw_socket,
        server_hostname="smtp.example",
    )


def test_starttls_failure_never_authenticates_or_sends(monkeypatch):
    server = MagicMock()
    server.starttls.side_effect = smtplib.SMTPNotSupportedError("STARTTLS unavailable")
    monkeypatch.setattr(smtp_policy, "_open_smtp_connection", MagicMock(return_value=server))
    target = ResolvedSmtpTarget("smtp.example", 587, ("1.1.1.1",))

    with pytest.raises(smtplib.SMTPNotSupportedError):
        _send_resolved_smtp_message(
            target,
            username="user@example.com",
            password="secret",
            recipient="to@example.com",
            message="message",
            timeout=10.0,
        )

    server.login.assert_not_called()
    server.sendmail.assert_not_called()
    server.close.assert_called_once()


def test_port_465_uses_implicit_tls_without_starttls(monkeypatch):
    server = MagicMock()
    open_connection = MagicMock(return_value=server)
    monkeypatch.setattr(smtp_policy, "_open_smtp_connection", open_connection)
    target = ResolvedSmtpTarget("smtp.example", 465, ("1.1.1.1",))

    _send_resolved_smtp_message(
        target,
        username="user@example.com",
        password="secret",
        recipient="to@example.com",
        message="message",
        timeout=10.0,
    )

    server.starttls.assert_not_called()
    server.login.assert_called_once_with("user@example.com", "secret")
    server.sendmail.assert_called_once_with(
        "user@example.com",
        ["to@example.com"],
        "message",
    )


def test_smtp_connect_falls_back_only_before_authentication(monkeypatch):
    connected_server = MagicMock()
    connector = MagicMock(
        side_effect=[ConnectionRefusedError("refused"), connected_server]
    )
    monkeypatch.setattr(smtp_policy, "_PinnedSMTP", connector)
    target = ResolvedSmtpTarget(
        "smtp.example",
        587,
        ("1.1.1.1", "1.0.0.1"),
    )

    result = smtp_policy._open_smtp_connection(
        target,
        timeout=10.0,
        context=MagicMock(),
    )

    assert result is connected_server
    assert [call.args[1] for call in connector.call_args_list] == [
        "1.1.1.1",
        "1.0.0.1",
    ]


def test_smtp_certificate_failure_does_not_try_another_address(monkeypatch):
    connector = MagicMock(
        side_effect=ssl.SSLCertVerificationError("certificate mismatch")
    )
    monkeypatch.setattr(smtp_policy, "_PinnedSMTP_SSL", connector)
    target = ResolvedSmtpTarget(
        "smtp.example",
        465,
        ("1.1.1.1", "1.0.0.1"),
    )

    with pytest.raises(ssl.SSLCertVerificationError):
        smtp_policy._open_smtp_connection(
            target,
            timeout=10.0,
            context=MagicMock(),
        )

    connector.assert_called_once()


def test_email_entry_points_share_policy_sender_and_hide_internal_errors():
    service_source = (ROOT / "app/services/notification_service.py").read_text(encoding="utf-8")
    tool_source = (ROOT / "app/services/ai/tools/notification_tools.py").read_text(encoding="utf-8")

    assert "import smtplib" not in service_source
    assert "import smtplib" not in tool_source
    assert service_source.count("await send_smtp_message(") == 1
    assert "NotificationService.send_email_to(" in tool_source
    assert "server.starttls" not in service_source
    assert "server.starttls" not in tool_source
    assert "Error sending email: {str(e)}" not in tool_source
