from pathlib import Path

import pytest


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "db-prod/V119-add_database_tls_policy.sql",
        "db-prod-pg/V18-add_database_tls_policy.sql",
    ],
)
def test_database_tls_migration_adds_policy_fields_and_constraint(path):
    sql = (ROOT / path).read_text(encoding="utf-8").lower()

    assert "tls_mode" in sql
    assert "tls_ca_path" in sql
    assert "disabled" in sql
    assert "verify_ca" in sql
    assert "verify_identity" in sql
    assert "check" in sql
    assert "ck_meta_db_connection_tls_policy" in sql
    assert "tls_ca_path is not null" in sql or '"tls_ca_path" is not null' in sql


@pytest.mark.parametrize(
    "path",
    [
        "db-prod/V119-add_database_tls_policy.sql",
        "db-prod-pg/V18-add_database_tls_policy.sql",
    ],
)
def test_database_tls_migration_preserves_sqlserver_identity_verification(path):
    sql = (ROOT / path).read_text(encoding="utf-8").lower()

    assert "sqlserver" in sql
    assert "verify_identity" in sql
    assert "else 'disabled'" in sql
