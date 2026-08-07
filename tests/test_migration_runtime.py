import asyncio
import importlib.util
from pathlib import Path

import pytest

from scripts.migration_runtime import (
    DirtyMigrationState,
    DuplicateMigrationVersion,
    LedgerEntry,
    MigrationChecksumMismatch,
    MigrationLockUnavailable,
    MissingMigrationFile,
    discover_migrations,
    plan_migrations,
    validate_ledger_history,
)


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration(tmp_path: Path, name: str, sql: str = "SELECT 1;") -> Path:
    path = tmp_path / name
    path.write_text(sql, encoding="utf-8")
    return path


def _entry(migration, status="success", checksum=None):
    return LedgerEntry(
        version=migration.version,
        description=migration.description,
        checksum=checksum or migration.checksum,
        status=status,
    )


def test_manifest_uses_natural_version_order_and_rejects_duplicates(tmp_path):
    v10 = _migration(tmp_path, "V10-later.sql")
    v31 = _migration(tmp_path, "V3.1-patch.sql")
    v3 = _migration(tmp_path, "V3-base.sql")

    manifest = discover_migrations([v10, v31, v3])
    assert [migration.version for migration in manifest] == ["3", "3.1", "10"]

    duplicate = _migration(tmp_path, "V3-other.sql")
    with pytest.raises(DuplicateMigrationVersion):
        discover_migrations([v3, duplicate])


def test_fresh_rerun_and_baseline_plans_are_explicit(tmp_path):
    migration = discover_migrations([_migration(tmp_path, "V1-init.sql")])[0]

    assert [action.kind for action in plan_migrations([migration], {})] == ["apply"]
    assert [
        action.kind
        for action in plan_migrations([migration], {}, baseline_existing=True)
    ] == ["baseline"]
    assert [
        action.kind
        for action in plan_migrations(
            [migration],
            {migration.version: _entry(migration)},
        )
    ] == ["skip"]


def test_baseline_through_adopts_history_and_applies_newer_versions(tmp_path):
    migrations = discover_migrations(
        [
            _migration(tmp_path, "V3-next.sql"),
            _migration(tmp_path, "V1-init.sql"),
            _migration(tmp_path, "V2-current.sql"),
        ]
    )

    actions = plan_migrations(migrations, {}, baseline_through="2")

    assert [(action.migration.version, action.kind) for action in actions] == [
        ("1", "baseline"),
        ("2", "baseline"),
        ("3", "apply"),
    ]


def test_n_minus_one_upgrade_skips_applied_version_and_applies_next(tmp_path):
    migrations = discover_migrations(
        [
            _migration(tmp_path, "V1-init.sql"),
            _migration(tmp_path, "V2-upgrade.sql"),
        ]
    )
    ledger = {"1": _entry(migrations[0])}

    actions = plan_migrations(migrations, ledger)

    assert [(action.migration.version, action.kind) for action in actions] == [
        ("1", "skip"),
        ("2", "apply"),
    ]


@pytest.mark.parametrize("version", ["V2", "2.x", "1.2.3", ""])
def test_baseline_through_rejects_invalid_version(tmp_path, version):
    migration = discover_migrations([_migration(tmp_path, "V1-init.sql")])

    with pytest.raises(ValueError):
        plan_migrations(migration, {}, baseline_through=version)


def test_baseline_through_rejects_version_missing_from_selected_manifest(tmp_path):
    migrations = discover_migrations(
        [
            _migration(tmp_path, "V1-init.sql"),
            _migration(tmp_path, "V3-next.sql"),
        ]
    )

    with pytest.raises(ValueError, match="不在本次迁移清单中"):
        plan_migrations(migrations, {}, baseline_through="2")


def test_tampered_migration_checksum_is_rejected(tmp_path):
    path = _migration(tmp_path, "V1-init.sql", "SELECT 1;")
    original = discover_migrations([path])[0]
    ledger = {original.version: _entry(original)}

    path.write_text("SELECT 2;", encoding="utf-8")
    changed = discover_migrations([path])[0]

    with pytest.raises(MigrationChecksumMismatch):
        plan_migrations([changed], ledger)
    with pytest.raises(MigrationChecksumMismatch):
        validate_ledger_history([changed], ledger)


@pytest.mark.parametrize("status", ["in_progress", "failed"])
def test_dirty_migration_never_retries_automatically(tmp_path, status):
    migration = discover_migrations([_migration(tmp_path, "V1-init.sql")])[0]

    with pytest.raises(DirtyMigrationState):
        plan_migrations(
            [migration],
            {migration.version: _entry(migration, status=status)},
        )


def test_applied_ledger_version_cannot_disappear_from_repository(tmp_path):
    migration = discover_migrations([_migration(tmp_path, "V1-init.sql")])[0]

    with pytest.raises(MissingMigrationFile):
        validate_ledger_history([], {migration.version: _entry(migration)})


def test_repository_manifests_have_unique_versions():
    mysql = discover_migrations((ROOT / "db-prod").glob("V*.sql"))
    postgres = discover_migrations((ROOT / "db-prod-pg").glob("V*.sql"))

    assert any(migration.version == "3.1" for migration in mysql)
    assert any(migration.version == "111.1" for migration in mysql)
    assert mysql[-1].version == "119"
    assert postgres[-1].version == "18"


class _AsyncLockCursor:
    async def execute(self, statement, parameters):
        self.statement = statement
        self.parameters = parameters

    async def fetchone(self):
        return (0,)


def test_mysql_concurrent_runner_fails_when_advisory_lock_is_busy():
    module = _load_module("mysql_migration_lock", "db-prod/apply_sql.py")
    cursor = _AsyncLockCursor()

    with pytest.raises(MigrationLockUnavailable):
        asyncio.run(module._acquire_lock(cursor, "nanzi_test", 0))
    assert "GET_LOCK" in cursor.statement


class _PgResult:
    def fetchone(self):
        return (False,)


class _PgLockConnection:
    def execute(self, statement, parameters):
        self.statement = statement
        self.parameters = parameters
        return _PgResult()


def test_postgres_concurrent_runner_fails_when_advisory_lock_is_busy():
    module = _load_module("pg_migration_lock", "db-prod-pg/apply_sql.py")
    connection = _PgLockConnection()

    with pytest.raises(MigrationLockUnavailable):
        module._acquire_lock(connection, "nanzi_test", 0)
    assert "pg_try_advisory_lock" in connection.statement


def test_importers_use_one_ledger_and_do_not_swallow_mysql_ddl_errors():
    mysql = (ROOT / "db-prod/apply_sql.py").read_text(encoding="utf-8")
    postgres = (ROOT / "db-prod-pg/apply_sql.py").read_text(encoding="utf-8")
    native = (ROOT / "db-prod/apply-sql-native.sh").read_text(encoding="utf-8")

    for source in (mysql, postgres):
        assert "nanzi_schema_migrations" in source
        assert "checksum" in source
        assert "in_progress" in source
        assert "failed" in source
    assert "IGNORED_ERRORS" not in mysql
    assert "apply-sql.sh" in native
    assert "advisory lock" in native
