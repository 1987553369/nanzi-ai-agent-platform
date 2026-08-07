import ssl
from pathlib import Path

import pytest

import app.utils.database_tls as database_tls


pytestmark = pytest.mark.no_infrastructure


@pytest.mark.parametrize(
    ("db_type", "mode"),
    [
        ("mysql", "verify_ca"),
        ("clickhouse", "verify_ca"),
        ("oracle", "verify_ca"),
        ("postgresql", "verify_ca"),
        ("postgresql", "verify_identity"),
        ("sqlserver", "verify_identity"),
    ],
)
def test_supported_tls_modes_are_explicit(db_type, mode):
    ca_path = "root.pem" if db_type != "sqlserver" else ""
    assert database_tls.validate_database_tls_config(
        db_type, mode, ca_path, require_tls=True
    )[0] == mode


@pytest.mark.parametrize("db_type", ["mysql", "clickhouse", "oracle"])
def test_fixed_ip_drivers_do_not_claim_identity_verification(db_type):
    with pytest.raises(ValueError, match="不支持 TLS 模式"):
        database_tls.validate_database_tls_config(
            db_type, "verify_identity", "root.pem", require_tls=True
        )


def test_production_policy_rejects_disabled_tls():
    with pytest.raises(ValueError, match="强制数据源 TLS"):
        database_tls.validate_database_tls_config(
            "postgresql", "disabled", require_tls=True
        )


@pytest.mark.parametrize("path", ["/tmp/root.pem", "../root.pem", "certs/../../root.pem"])
def test_ca_path_rejects_absolute_and_parent_segments(path):
    with pytest.raises(ValueError, match="相对路径"):
        database_tls.validate_database_tls_config(
            "mysql", "verify_ca", path, require_tls=False
        )


def test_ca_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    outside = tmp_path / "outside.pem"
    outside.write_text("not-a-certificate", encoding="utf-8")
    (root / "escape.pem").symlink_to(outside)

    with pytest.raises(ValueError, match="超出部署审批目录"):
        database_tls.resolve_database_tls_ca_path(
            "escape.pem", ca_dir=str(root)
        )


def test_driver_kwargs_share_verified_ca_path(tmp_path, monkeypatch):
    ca = tmp_path / "root.pem"
    ca.write_text("test-ca", encoding="utf-8")
    monkeypatch.setattr(database_tls, "_runtime_policy", lambda: (False, str(tmp_path)))
    sentinel = object()
    monkeypatch.setattr(database_tls, "_client_ssl_context", lambda path, **kwargs: sentinel)
    config = {"tls_mode": "verify_ca", "tls_ca_path": "root.pem"}

    assert database_tls.build_mysql_tls_kwargs(config) == {"ssl": sentinel}
    assert database_tls.build_clickhouse_tls_kwargs(config) == {
        "secure": True,
        "verify": True,
        "ca_certs": str(ca),
    }
    assert database_tls.build_postgresql_tls_kwargs(config) == {
        "sslmode": "verify-ca",
        "sslrootcert": str(ca),
    }
    dsn, kwargs = database_tls.build_oracle_tls_connection(
        {**config, "database": "ORCL"}, connect_address="192.0.2.10", port=2484
    )
    assert "(PROTOCOL=tcps)" in dsn
    assert kwargs == {"ssl_context": sentinel}


def test_postgresql_identity_mode_preserves_verify_full(tmp_path, monkeypatch):
    (tmp_path / "root.pem").write_text("test-ca", encoding="utf-8")
    monkeypatch.setattr(database_tls, "_runtime_policy", lambda: (False, str(tmp_path)))

    kwargs = database_tls.build_postgresql_tls_kwargs(
        {"tls_mode": "verify_identity", "tls_ca_path": "root.pem"}
    )

    assert kwargs["sslmode"] == "verify-full"


def test_oracle_thick_mode_requires_wallet_directory(tmp_path, monkeypatch):
    (tmp_path / "root.pem").write_text("test-ca", encoding="utf-8")
    wallet = tmp_path / "wallet"
    wallet.mkdir()
    monkeypatch.setattr(database_tls, "_runtime_policy", lambda: (False, str(tmp_path)))

    with pytest.raises(ValueError, match="Wallet 配置目录"):
        database_tls.build_oracle_tls_connection(
            {"database": "ORCL", "tls_mode": "verify_ca", "tls_ca_path": "root.pem"},
            connect_address="192.0.2.10",
            port=2484,
            use_thick_mode=True,
        )

    _, kwargs = database_tls.build_oracle_tls_connection(
        {"database": "ORCL", "tls_mode": "verify_ca", "tls_ca_path": "wallet"},
        connect_address="192.0.2.10",
        port=2484,
        use_thick_mode=True,
    )
    assert kwargs == {"config_dir": str(wallet), "wallet_location": str(wallet)}


@pytest.mark.parametrize("database", ["", "ORCL)(SECURITY=broken)", "../ORCL"])
def test_oracle_connection_identifier_cannot_inject_dsn(database):
    with pytest.raises(ValueError, match="Oracle SID/Service Name"):
        database_tls.build_oracle_tls_connection(
            {"database": database, "tls_mode": "disabled"},
            connect_address="192.0.2.10",
            port=1521,
        )


def test_ssl_context_requires_tls12_and_certificate_validation():
    default_ca = ssl.get_default_verify_paths().cafile
    if not default_ca or not Path(default_ca).is_file():
        pytest.skip("当前 Python 运行时没有可读取的系统 CA 文件")

    context = database_tls._client_ssl_context(default_ca)

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert context.check_hostname is False
