"""Apply versioned PostgreSQL migrations with a checksum ledger and advisory lock."""

import argparse
import getpass
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migration_runtime import (  # noqa: E402
    LedgerEntry,
    Migration,
    MigrationContractError,
    MigrationLockUnavailable,
    discover_migrations,
    migration_directories_manifest,
    plan_migrations,
    validate_ledger_history,
    version_sort_key,
)


DATABASE_SWITCH_RE = re.compile(
    r"^\s*(?:CREATE\s+DATABASE\b|DROP\s+DATABASE\b|ALTER\s+DATABASE\b|\\connect\b)",
    re.IGNORECASE,
)
DATABASE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROTECTED_DATABASES = frozenset({"postgres", "template0", "template1"})
LEDGER_TABLE = "nanzi_schema_migrations"


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def _psycopg():
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError(
            "缺少 psycopg；请在项目 Python 3.11 环境安装锁定依赖后重试"
        ) from exc
    return psycopg, sql


def validate_target_database(database: str) -> str:
    if not database or not DATABASE_NAME_RE.fullmatch(database):
        raise ValueError(
            "target database must be a non-empty PostgreSQL identifier "
            "containing only letters, digits, and underscores"
        )
    if database.lower() in PROTECTED_DATABASES:
        raise ValueError(f"refusing to modify protected PostgreSQL database: {database}")
    return database


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Apply checksum-verified SQL migrations to an explicit PostgreSQL database."
    )
    parser.add_argument("file_paths", nargs="+", help="Versioned SQL files to execute")
    parser.add_argument("--host", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--user", help="PostgreSQL user")
    parser.add_argument("--password", help="PostgreSQL password; omit with --interactive to prompt")
    parser.add_argument("--database", "--db", dest="database", help="Target database name")
    parser.add_argument("--lock-timeout", type=int, default=30, help="Advisory lock timeout in seconds")
    baseline_group = parser.add_mutually_exclusive_group()
    baseline_group.add_argument(
        "--baseline-existing",
        action="store_true",
        help="Record selected migrations without executing them; only for a verified existing schema",
    )
    baseline_group.add_argument(
        "--baseline-through",
        metavar="VERSION",
        help="Record missing migrations through VERSION, then execute later selected versions",
    )
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    missing = [name for name in ("host", "user", "database") if not getattr(args, name)]
    if missing and not args.interactive:
        parser.error(
            "missing explicit connection parameter(s): "
            + ", ".join(f"--{name}" for name in missing)
            + ". Use --interactive to enter them safely."
        )
    if args.lock_timeout < 0:
        parser.error("--lock-timeout must be zero or greater")
    if args.baseline_through is not None:
        try:
            version_sort_key(args.baseline_through)
        except ValueError as error:
            parser.error(str(error))
    return args


def prompt_if_missing(label, current, secret=False):
    if current is not None:
        return current
    if secret:
        return getpass.getpass(f"{label}: ")
    return input(f"{label}: ").strip()


def build_config(args) -> DbConfig:
    database = prompt_if_missing("Target database", args.database)
    password = args.password or os.environ.get("NANZI_MIGRATION_PASSWORD")
    return DbConfig(
        host=prompt_if_missing("PostgreSQL host", args.host),
        port=args.port,
        user=prompt_if_missing("PostgreSQL user", args.user),
        password=prompt_if_missing("PostgreSQL password", password, secret=True),
        database=validate_target_database(database),
    )


def _remove_comments(statement: str) -> str:
    result = []
    index = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    while index < len(statement):
        char = statement[index]
        next_char = statement[index + 1] if index + 1 < len(statement) else ""
        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
                result.append(char)
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if not in_double and not in_single and char == "-" and next_char == "-":
            in_line_comment = True
            index += 2
            continue
        if not in_double and not in_single and char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        result.append(char)
        if char == "'" and not in_double:
            if in_single and next_char == "'":
                result.append(next_char)
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            if in_double and next_char == '"':
                result.append(next_char)
                index += 2
                continue
            in_double = not in_double
        index += 1
    return "".join(result)


def _append_statement(statements, current):
    statement = "".join(current).strip()
    if not statement or not _remove_comments(statement).strip():
        return
    statement = statement.rstrip(";").rstrip()
    if DATABASE_SWITCH_RE.match(statement):
        print(f"Skipping database-switching statement: {statement.splitlines()[0]}")
        return
    statements.append(statement)


def split_sql_statements(sql_content: str):
    statements = []
    current = []
    index = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag = None
    while index < len(sql_content):
        char = sql_content[index]
        next_char = sql_content[index + 1] if index + 1 < len(sql_content) else ""
        if in_line_comment:
            current.append(char)
            if char in "\r\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if dollar_tag is not None:
            if sql_content.startswith(dollar_tag, index):
                current.extend(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                current.append(char)
                index += 1
            continue
        if not in_single and not in_double and char == "-" and next_char == "-":
            current.extend((char, next_char))
            in_line_comment = True
            index += 2
            continue
        if not in_single and not in_double and char == "/" and next_char == "*":
            current.extend((char, next_char))
            in_block_comment = True
            index += 2
            continue
        if not in_double and char == "'":
            current.append(char)
            if in_single and next_char == "'":
                current.append(next_char)
                index += 2
                continue
            in_single = not in_single
            index += 1
            continue
        if not in_single and char == '"':
            current.append(char)
            if in_double and next_char == '"':
                current.append(next_char)
                index += 2
                continue
            in_double = not in_double
            index += 1
            continue
        if not in_single and not in_double and char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql_content[index:])
            if match:
                dollar_tag = match.group(0)
                current.extend(dollar_tag)
                index += len(dollar_tag)
                continue
        if char == ";" and not in_single and not in_double:
            current.append(char)
            _append_statement(statements, current)
            current = []
        else:
            current.append(char)
        index += 1
    _append_statement(statements, current)
    return statements


def _connection_kwargs(config: DbConfig, database: str) -> dict:
    return {
        "host": config.host,
        "port": config.port,
        "user": config.user,
        "password": config.password,
        "dbname": database,
    }


def ensure_database(config: DbConfig) -> None:
    psycopg, sql = _psycopg()
    with psycopg.connect(**_connection_kwargs(config, "postgres"), autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config.database,),
        ).fetchone()
        if exists:
            return
        connection.execute(
            sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(
                sql.Identifier(config.database)
            )
        )


def confirm_execution(
    config,
    file_paths,
    *,
    baseline_existing=False,
    baseline_through=None,
):
    paths = [file_paths] if isinstance(file_paths, (str, os.PathLike)) else file_paths
    print("请确认本次 SQL 执行目标：")
    print(f"  Host     : {config.host}")
    print(f"  Port     : {config.port}")
    print(f"  User     : {config.user}")
    print(f"  Database : {config.database}")
    if baseline_existing:
        mode = "BASELINE（选中文件仅登记，不执行）"
    elif baseline_through is not None:
        mode = f"ADOPT THROUGH V{baseline_through}，随后执行更高版本"
    else:
        mode = "APPLY"
    print(f"  Mode     : {mode}")
    print("  SQL files:")
    for path in paths:
        print(f"    - {path}")
    print("  Password : ******")
    answer = input("确认无误请输入 YES 继续执行：").strip()
    if answer.upper() != "YES":
        print("已取消，未执行 SQL。")
        raise SystemExit(1)


def _lock_key(database: str) -> int:
    return int.from_bytes(
        hashlib.sha256(database.encode("utf-8")).digest()[:8],
        "big",
        signed=True,
    )


def _acquire_lock(connection, database: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        row = connection.execute(
            "SELECT pg_try_advisory_lock(%s)",
            (_lock_key(database),),
        ).fetchone()
        if row and row[0] is True:
            return
        if time.monotonic() >= deadline:
            raise MigrationLockUnavailable(
                f"无法获取数据库 {database} 的迁移锁；已有迁移进程正在运行"
            )
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))


def _release_lock(connection, database: str) -> None:
    connection.execute("SELECT pg_advisory_unlock(%s)", (_lock_key(database),))


def _ensure_ledger(connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            installed_rank BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            version VARCHAR(50) NOT NULL UNIQUE,
            description VARCHAR(255) NOT NULL,
            checksum CHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            installed_by VARCHAR(128) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            installed_on TIMESTAMPTZ NULL,
            execution_ms BIGINT NULL,
            error_message TEXT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_nanzi_schema_migrations_status "
        f"ON {LEDGER_TABLE} (status)"
    )


def _load_ledger(connection) -> Dict[str, LedgerEntry]:
    rows = connection.execute(
        f"SELECT version, description, checksum, status FROM {LEDGER_TABLE}"
    ).fetchall()
    return {
        str(row[0]): LedgerEntry(
            version=str(row[0]),
            description=str(row[1]),
            checksum=str(row[2]),
            status=str(row[3]),
        )
        for row in rows
    }


def _has_existing_schema(connection) -> bool:
    row = connection.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> %s",
        (LEDGER_TABLE,),
    ).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _record_baseline(connection, migration: Migration, installed_by: str) -> None:
    connection.execute(
        f"""
        INSERT INTO {LEDGER_TABLE}
            (version, description, checksum, status, installed_by, installed_on, execution_ms)
        VALUES (%s, %s, %s, 'baseline', %s, CURRENT_TIMESTAMP, 0)
        """,
        (migration.version, migration.description, migration.checksum, installed_by),
    )


def _mark_failed(connection, migration: Migration, installed_by: str, execution_ms: int, error: Exception) -> None:
    connection.execute(
        f"""
        INSERT INTO {LEDGER_TABLE}
            (version, description, checksum, status, installed_by, installed_on,
             execution_ms, error_message)
        VALUES (%s, %s, %s, 'failed', %s, CURRENT_TIMESTAMP, %s, %s)
        ON CONFLICT (version) DO UPDATE SET
            status = 'failed', installed_on = CURRENT_TIMESTAMP,
            execution_ms = EXCLUDED.execution_ms,
            error_message = EXCLUDED.error_message
        """,
        (
            migration.version,
            migration.description,
            migration.checksum,
            installed_by,
            execution_ms,
            str(error)[:4000],
        ),
    )


def _execute_migration(connection, migration: Migration, installed_by: str) -> None:
    statements = split_sql_statements(migration.path.read_text(encoding="utf-8"))
    started = time.monotonic()
    try:
        with connection.transaction():
            connection.execute(
                f"""
                INSERT INTO {LEDGER_TABLE}
                    (version, description, checksum, status, installed_by)
                VALUES (%s, %s, %s, 'in_progress', %s)
                """,
                (migration.version, migration.description, migration.checksum, installed_by),
            )
            print(f"Applying V{migration.version} {migration.description} ({len(statements)} statements)")
            for index, statement in enumerate(statements, start=1):
                cursor = connection.execute(statement)
                print(f"   -> #{index}: affected rows {cursor.rowcount}")
            execution_ms = int((time.monotonic() - started) * 1000)
            connection.execute(
                f"""
                UPDATE {LEDGER_TABLE}
                SET status = 'success', installed_on = CURRENT_TIMESTAMP,
                    execution_ms = %s, error_message = NULL
                WHERE version = %s AND checksum = %s AND status = 'in_progress'
                """,
                (execution_ms, migration.version, migration.checksum),
            )
    except Exception as error:
        execution_ms = int((time.monotonic() - started) * 1000)
        with connection.transaction():
            _mark_failed(connection, migration, installed_by, execution_ms, error)
        raise


def apply_sql(
    file_paths: Sequence[str],
    config: DbConfig,
    *,
    baseline_existing: bool = False,
    baseline_through: str = None,
    lock_timeout: int = 30,
) -> None:
    paths = [file_paths] if isinstance(file_paths, (str, os.PathLike)) else file_paths
    migrations = discover_migrations(Path(path) for path in paths)
    directory_manifest = migration_directories_manifest(migrations)
    ensure_database(config)
    psycopg, _ = _psycopg()
    with psycopg.connect(**_connection_kwargs(config, config.database)) as connection:
        _acquire_lock(connection, config.database, lock_timeout)
        try:
            _ensure_ledger(connection)
            connection.commit()
            ledger = _load_ledger(connection)
            validate_ledger_history(directory_manifest, ledger)
            has_existing_schema = _has_existing_schema(connection)
            adoption_mode = baseline_existing or baseline_through is not None
            if not ledger and has_existing_schema and not adoption_mode:
                raise MigrationContractError(
                    "检测到已有业务表但迁移账本为空；禁止从 V0 自动重放。"
                    "请备份并核对当前版本后，使用 --baseline-through 显式登记"
                )
            actions = plan_migrations(
                migrations,
                ledger,
                baseline_existing=baseline_existing,
                baseline_through=baseline_through,
            )
            if adoption_mode and not has_existing_schema:
                raise MigrationContractError(
                    "基线模式只能用于已有业务表的数据库，拒绝为空库建立假账本"
                )
            connection.commit()
            for action in actions:
                migration = action.migration
                if action.kind == "skip":
                    print(f"Skipping V{migration.version}: checksum verified")
                elif action.kind == "baseline":
                    with connection.transaction():
                        _record_baseline(connection, migration, config.user)
                    print(f"Baselined V{migration.version}: {migration.description}")
                else:
                    _execute_migration(connection, migration, config.user)
        finally:
            _release_lock(connection, config.database)
            connection.commit()


def main(argv=None):
    args = parse_args(argv)
    try:
        config = build_config(args)
        migrations = discover_migrations(Path(path) for path in args.file_paths)
        if not args.yes:
            confirm_execution(
                config,
                [migration.path for migration in migrations],
                baseline_existing=args.baseline_existing,
                baseline_through=args.baseline_through,
            )
        apply_sql(
            [str(migration.path) for migration in migrations],
            config,
            baseline_existing=args.baseline_existing,
            baseline_through=args.baseline_through,
            lock_timeout=args.lock_timeout,
        )
    except (FileNotFoundError, MigrationContractError, RuntimeError, ValueError) as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
