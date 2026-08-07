import asyncio
import socket
from pathlib import Path

import pytest

from app.utils.database_outbound import (
    DatabaseOutboundPolicyError,
    resolve_database_target,
    validate_database_allowed_ports,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


def _resolve(hostname, port=5432, **overrides):
    options = {
        "allowed_private_hosts": [],
        "allowed_private_cidrs": [],
        "allowed_ports": [1433, 1521, 3306, 5432, 9000],
    }
    options.update(overrides)
    return asyncio.run(resolve_database_target(hostname, port, **options))


def test_database_target_resolves_all_addresses_and_pins_one(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert (host, port, type) == ("db.example", 5432, socket.SOCK_STREAM)
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    target = _resolve("DB.Example.")

    assert target.hostname == "db.example"
    assert target.addresses == ("2606:4700:4700::1111", "1.1.1.1")
    assert target.connect_address == "1.1.1.1"


def test_database_private_target_requires_exact_host_and_cidr(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port))
        ],
    )

    with pytest.raises(DatabaseOutboundPolicyError, match="私网审批"):
        _resolve("db.internal")
    with pytest.raises(DatabaseOutboundPolicyError, match="私网审批"):
        _resolve(
            "other.internal",
            allowed_private_hosts=["db.internal"],
            allowed_private_cidrs=["10.20.1.0/24"],
        )

    target = _resolve(
        "db.internal",
        allowed_private_hosts=["db.internal"],
        allowed_private_cidrs=["10.20.1.0/24"],
    )
    assert target.connect_address == "10.20.1.8"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "169.254.169.254", "::1", "fe80::1"],
)
def test_database_target_rejects_loopback_and_link_local(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 5432, 0, 0) if family == socket.AF_INET6 else (address, 5432)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [(family, socket.SOCK_STREAM, 6, "", sockaddr)],
    )

    with pytest.raises(DatabaseOutboundPolicyError):
        _resolve("db.example")


def test_database_target_rejects_mixed_public_private_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.1.8", port)),
        ],
    )

    with pytest.raises(DatabaseOutboundPolicyError):
        _resolve(
            "db.internal",
            allowed_private_hosts=["db.internal"],
            allowed_private_cidrs=["10.20.1.0/24"],
        )


def test_database_target_rejects_unapproved_port_before_dns(monkeypatch):
    called = False

    def fake_getaddrinfo(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DatabaseOutboundPolicyError, match="端口未通过部署审批"):
        _resolve("db.example", 27017)
    assert called is False


@pytest.mark.parametrize(
    "hostname",
    [
        "https://db.example",
        "db.example/path",
        "user@db.example",
        "*.db.example",
        "db.example:5432",
        "[not-ipv6]",
        "fe80::1%eth0",
    ],
)
def test_database_target_rejects_unsafe_host_syntax_before_dns(monkeypatch, hostname):
    called = False

    def fake_getaddrinfo(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(DatabaseOutboundPolicyError, match="主机名格式无效"):
        _resolve(hostname)
    assert called is False


def test_database_port_policy_rejects_empty_invalid_and_boolean_values():
    for ports in ([], [0], [65536], [True]):
        with pytest.raises(DatabaseOutboundPolicyError):
            validate_database_allowed_ports(ports)


def test_native_database_entry_points_use_resolved_targets():
    pool_source = (ROOT / "app/services/pool_manager.py").read_text(encoding="utf-8")
    import_source = (ROOT / "app/services/db_import_service.py").read_text(encoding="utf-8")
    postgresql_source = (ROOT / "app/services/data_adapter/postgresql.py").read_text(encoding="utf-8")
    sqlserver_source = (ROOT / "app/services/data_adapter/sqlserver.py").read_text(encoding="utf-8")

    assert pool_source.count("resolve_database_target(") == 5
    assert import_source.count("resolve_database_target(") == 5
    assert 'conninfo["hostaddr"] = connect_address' in postgresql_source
    assert import_source.count("connect_address=target.connect_address") >= 2
    assert "TrustServerCertificate=yes" not in sqlserver_source
    assert '"Encrypt=yes;"' in sqlserver_source
    assert '"TrustServerCertificate=no;"' in sqlserver_source
    assert "HostNameInCertificate=" in sqlserver_source
    assert '连接失败: {str(e)}' not in import_source
    assert '表列表失败: {str(e)}' not in import_source
    assert 'DDL 失败: {str(e)}' not in import_source
