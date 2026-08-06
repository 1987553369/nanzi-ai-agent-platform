"""Apply versioned MySQL migrations with a checksum ledger and advisory lock."""

import argparse
import asyncio
import getpass
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


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


DATABASE_SWITCH_RE = re.compile(r"^\s*(CREATE\s+DATABASE\b|USE\b)", re.IGNORECASE)
DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
LEDGER_TABLE = "nanzi_schema_migrations"


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def _aiomysql():
    try:
        import aiomysql
    except ImportError as exc:
        raise RuntimeError(
            "缺少 aiomysql；请在项目 Python 3.11 环境安装锁定依赖后重试"
        ) from exc
    return aiomysql


def validate_target_database(database: str) -> str:
    if not database or not DATABASE_NAME_RE.fullmatch(database):
        raise ValueError("target database must contain only letters, digits, and underscores")
    return database


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Apply checksum-verified SQL migrations to an explicit MySQL database."
    )
    parser.add_argument("file_paths", nargs="+", help="Versioned SQL files to execute")
    parser.add_argument("--host", help="MySQL host")
    parser.add_argument("--port", type=int, default=3306, help="MySQL port")
    parser.add_argument("--user", help="MySQL user")
    parser.add_argument("--password", help="MySQL password; omit with --interactive to prompt")
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


def build_config(args):
    database = prompt_if_missing("Target database", args.database)
    password = args.password or os.environ.get("NANZI_MIGRATION_PASSWORD")
    return DbConfig(
        host=prompt_if_missing("MySQL host", args.host),
        port=args.port,
        user=prompt_if_missing("MySQL user", args.user),
        password=prompt_if_missing("MySQL password", password, secret=True),
        database=validate_target_database(database),
    )


def split_sql_statements(sql_content):
    statements = []
    current_statement = []
    in_string = False
    escape = False
    quote_char = None

    for char in sql_content:
        current_statement.append(char)
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char in ("'", '"', "`"):
            if not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char:
                in_string = False
                quote_char = None
        elif char == ";" and not in_string:
            _append_mysql_statement(statements, current_statement)
            current_statement = []
    _append_mysql_statement(statements, current_statement)
    return statements


def _append_mysql_statement(statements, current_statement):
    if not current_statement:
        return
    statement = "".join(current_statement).strip()
    lines = [
        line
        for line in statement.splitlines()
        if not line.strip().startswith(("--", "#"))
    ]
    clean_statement = "\n".join(lines).strip().rstrip(";").strip()
    if not clean_statement:
        return
    if DATABASE_SWITCH_RE.match(clean_statement):
        print(f"Skipping database-switching statement: {clean_statement.splitlines()[0]}")
        return
    statements.append(clean_statement)


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


def _lock_name(database: str) -> str:
    digest = hashlib.sha256(database.encode("utf-8")).hexdigest()[:32]
    return f"nanzi:migration:{digest}"


async def _ensure_database(config: DbConfig) -> None:
    aiomysql = _aiomysql()
    connection = await aiomysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
    finally:
        connection.close()
        await connection.ensure_closed()


async def _acquire_lock(cursor, database: str, timeout: int) -> None:
    await cursor.execute("SELECT GET_LOCK(%s, %s)", (_lock_name(database), timeout))
    row = await cursor.fetchone()
    if not row or int(row[0] or 0) != 1:
        raise MigrationLockUnavailable(
            f"无法获取数据库 {database} 的迁移锁；已有迁移进程正在运行"
        )


async def _release_lock(cursor, database: str) -> None:
    await cursor.execute("SELECT RELEASE_LOCK(%s)", (_lock_name(database),))


async def _ensure_ledger(cursor) -> None:
    await cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            installed_rank BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            version VARCHAR(50) NOT NULL UNIQUE,
            description VARCHAR(255) NOT NULL,
            checksum CHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            installed_by VARCHAR(128) NOT NULL,
            started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            installed_on DATETIME(6) NULL,
            execution_ms BIGINT NULL,
            error_message TEXT NULL,
            INDEX idx_nanzi_schema_migrations_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


async def _load_ledger(cursor) -> Dict[str, LedgerEntry]:
    await cursor.execute(
        f"SELECT version, description, checksum, status FROM {LEDGER_TABLE}"
    )
    rows = await cursor.fetchall()
    return {
        str(row[0]): LedgerEntry(
            version=str(row[0]),
            description=str(row[1]),
            checksum=str(row[2]),
            status=str(row[3]),
        )
        for row in rows
    }


async def _has_existing_schema(cursor, database: str) -> bool:
    await cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name <> %s",
        (database, LEDGER_TABLE),
    )
    row = await cursor.fetchone()
    return bool(row and int(row[0] or 0) > 0)


async def _record_baseline(cursor, migration: Migration, installed_by: str) -> None:
    await cursor.execute(
        f"""
        INSERT INTO {LEDGER_TABLE}
            (version, description, checksum, status, installed_by, installed_on, execution_ms)
        VALUES (%s, %s, %s, 'baseline', %s, NOW(6), 0)
        """,
        (migration.version, migration.description, migration.checksum, installed_by),
    )


async def _mark_started(cursor, migration: Migration, installed_by: str) -> None:
    await cursor.execute(
        f"""
        INSERT INTO {LEDGER_TABLE}
            (version, description, checksum, status, installed_by)
        VALUES (%s, %s, %s, 'in_progress', %s)
        """,
        (migration.version, migration.description, migration.checksum, installed_by),
    )


async def _mark_finished(cursor, migration: Migration, execution_ms: int) -> None:
    await cursor.execute(
        f"""
        UPDATE {LEDGER_TABLE}
        SET status = 'success', installed_on = NOW(6), execution_ms = %s,
            error_message = NULL
        WHERE version = %s AND checksum = %s AND status = 'in_progress'
        """,
        (execution_ms, migration.version, migration.checksum),
    )


async def _mark_failed(cursor, migration: Migration, execution_ms: int, error: Exception) -> None:
    await cursor.execute(
        f"""
        UPDATE {LEDGER_TABLE}
        SET status = 'failed', installed_on = NOW(6), execution_ms = %s,
            error_message = %s
        WHERE version = %s AND checksum = %s
        """,
        (execution_ms, str(error)[:4000], migration.version, migration.checksum),
    )


async def _execute_migration(connection, cursor, migration: Migration, installed_by: str) -> None:
    statements = split_sql_statements(migration.path.read_text(encoding="utf-8"))
    started = time.monotonic()
    await _mark_started(cursor, migration, installed_by)
    await connection.commit()
    try:
        print(f"Applying V{migration.version} {migration.description} ({len(statements)} statements)")
        for index, statement in enumerate(statements, start=1):
            await cursor.execute(statement)
            print(f"   -> #{index}: affected rows {cursor.rowcount}")
    except Exception as error:
        execution_ms = int((time.monotonic() - started) * 1000)
        await connection.rollback()
        await _mark_failed(cursor, migration, execution_ms, error)
        await connection.commit()
        raise
    execution_ms = int((time.monotonic() - started) * 1000)
    await _mark_finished(cursor, migration, execution_ms)
    await connection.commit()


async def apply_sql(
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
    await _ensure_database(config)
    aiomysql = _aiomysql()
    pool = await aiomysql.create_pool(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        db=config.database,
        autocommit=False,
        minsize=1,
        maxsize=1,
    )
    try:
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await _acquire_lock(cursor, config.database, lock_timeout)
                try:
                    await _ensure_ledger(cursor)
                    await connection.commit()
                    ledger = await _load_ledger(cursor)
                    validate_ledger_history(directory_manifest, ledger)
                    has_existing_schema = await _has_existing_schema(cursor, config.database)
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
                    for action in actions:
                        migration = action.migration
                        if action.kind == "skip":
                            print(f"Skipping V{migration.version}: checksum verified")
                        elif action.kind == "baseline":
                            await _record_baseline(cursor, migration, config.user)
                            await connection.commit()
                            print(f"Baselined V{migration.version}: {migration.description}")
                        else:
                            await _execute_migration(connection, cursor, migration, config.user)
                finally:
                    await _release_lock(cursor, config.database)
    finally:
        pool.close()
        await pool.wait_closed()


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
        asyncio.run(
            apply_sql(
                [str(migration.path) for migration in migrations],
                config,
                baseline_existing=args.baseline_existing,
                baseline_through=args.baseline_through,
                lock_timeout=args.lock_timeout,
            )
        )
    except (FileNotFoundError, MigrationContractError, RuntimeError, ValueError) as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
