from pathlib import Path

import pytest


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_database_connection_paths_use_shared_tls_builders():
    pool = _source("app/services/pool_manager.py")
    imports = _source("app/services/db_import_service.py")
    postgresql = _source("app/services/data_adapter/postgresql.py")
    sqlserver = _source("app/services/data_adapter/sqlserver.py")

    for builder in (
        "build_mysql_tls_kwargs",
        "build_clickhouse_tls_kwargs",
        "build_oracle_tls_connection",
    ):
        assert builder in pool
        assert builder in imports
    assert "build_postgresql_tls_kwargs" in postgresql
    assert "validate_sqlserver_tls" in sqlserver
    assert "_get_oracle_connect_args(self.config)" in imports


def test_frontend_exposes_only_driver_supported_modes_and_retests_tls_changes():
    source = _source("frontend/src/views/DataSourceManagement.vue")

    assert "form.type === 'postgresql'" in source
    assert "form.type === 'sqlserver'" in source
    assert "verify_identity" in source
    assert "tlsCaPath" in source
    assert "original.tls_mode !== form.tlsMode" in source
    assert "DATA_SOURCE_TLS_CA_DIR" in source
    assert "生产部署会拒绝此配置" in source


def test_production_compose_enforces_tls_and_mounts_ca_read_only():
    compose = _source("docker/docker-compose.ai-agent.yml")

    assert "DATA_SOURCE_REQUIRE_TLS=${DATA_SOURCE_REQUIRE_TLS:-true}" in compose
    assert "./certs/data-sources:/app/certs/data-sources:ro" in compose


def test_sqlserver_contract_still_requires_certificate_identity():
    source = _source("app/services/data_adapter/sqlserver.py")

    assert "Encrypt=yes;" in source
    assert "TrustServerCertificate=no;" in source
    assert "HostNameInCertificate=" in source
