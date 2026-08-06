"""Shared manifest and ledger rules for production database migrations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


MIGRATION_FILENAME_RE = re.compile(
    r"^V(?P<version>\d+(?:\.\d+)?)[-_](?P<description>.+)\.sql$",
    re.IGNORECASE,
)
SUCCESSFUL_STATUSES = frozenset({"success", "baseline"})


class MigrationContractError(RuntimeError):
    """Base class for migration manifest and ledger violations."""


class InvalidMigrationFilename(MigrationContractError):
    pass


class DuplicateMigrationVersion(MigrationContractError):
    pass


class MigrationChecksumMismatch(MigrationContractError):
    pass


class DirtyMigrationState(MigrationContractError):
    pass


class MissingMigrationFile(MigrationContractError):
    pass


class MigrationLockUnavailable(MigrationContractError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    path: Path
    checksum: str
    sort_key: Tuple[int, ...]


@dataclass(frozen=True)
class LedgerEntry:
    version: str
    description: str
    checksum: str
    status: str


@dataclass(frozen=True)
class MigrationAction:
    kind: str
    migration: Migration


def _canonical_version(raw: str) -> Tuple[str, Tuple[int, ...]]:
    if not re.fullmatch(r"\d+(?:\.\d+)?", str(raw or "")):
        raise ValueError(f"无效迁移版本：{raw}")
    parts = tuple(int(part) for part in raw.split("."))
    return ".".join(str(part) for part in parts), parts


def version_sort_key(raw: str) -> Tuple[int, ...]:
    return _canonical_version(raw)[1]


def parse_migration(path: Path) -> Migration:
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    match = MIGRATION_FILENAME_RE.fullmatch(candidate.name)
    if match is None:
        raise InvalidMigrationFilename(
            f"迁移文件名必须符合 V<版本>-<描述>.sql：{candidate.name}"
        )
    version, sort_key = _canonical_version(match.group("version"))
    return Migration(
        version=version,
        description=match.group("description"),
        path=candidate,
        checksum=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        sort_key=sort_key,
    )


def discover_migrations(paths: Iterable[Path]) -> List[Migration]:
    migrations = [parse_migration(Path(path)) for path in paths]
    versions: Dict[str, List[Path]] = {}
    for migration in migrations:
        versions.setdefault(migration.version, []).append(migration.path)
    duplicates = {
        version: version_paths
        for version, version_paths in versions.items()
        if len(version_paths) > 1
    }
    if duplicates:
        details = "; ".join(
            f"V{version}: {', '.join(path.name for path in version_paths)}"
            for version, version_paths in sorted(duplicates.items())
        )
        raise DuplicateMigrationVersion(f"检测到重复迁移版本：{details}")
    return sorted(migrations, key=lambda item: (item.sort_key, item.path.name))


def migration_directories_manifest(migrations: Sequence[Migration]) -> List[Migration]:
    paths = []
    seen = set()
    for migration in migrations:
        directory = migration.path.parent
        if directory in seen:
            continue
        seen.add(directory)
        paths.extend(directory.glob("V*.sql"))
    return discover_migrations(paths)


def validate_ledger_history(
    manifest: Sequence[Migration],
    ledger: Mapping[str, LedgerEntry],
) -> None:
    by_version = {migration.version: migration for migration in manifest}
    for version, entry in ledger.items():
        migration = by_version.get(version)
        if migration is None:
            raise MissingMigrationFile(
                f"账本中的 V{version} 已执行，但当前代码中缺少对应迁移文件"
            )
        if migration.checksum != entry.checksum:
            raise MigrationChecksumMismatch(
                f"迁移 V{version} 校验和已变化；禁止修改已执行迁移，请新增版本"
            )


def plan_migrations(
    migrations: Sequence[Migration],
    ledger: Mapping[str, LedgerEntry],
    *,
    baseline_existing: bool = False,
    baseline_through: Optional[str] = None,
) -> List[MigrationAction]:
    actions = []
    baseline_limit = (
        version_sort_key(baseline_through)
        if baseline_through is not None
        else None
    )
    if baseline_limit is not None and not any(
        migration.sort_key == baseline_limit for migration in migrations
    ):
        raise ValueError(
            f"基线截止版本 V{baseline_through} 不在本次迁移清单中；"
            "请核对版本并使用包含该版本的全量迁移入口"
        )
    for migration in migrations:
        entry = ledger.get(migration.version)
        if entry is None:
            should_baseline = baseline_existing or (
                baseline_limit is not None and migration.sort_key <= baseline_limit
            )
            actions.append(
                MigrationAction(
                    kind="baseline" if should_baseline else "apply",
                    migration=migration,
                )
            )
            continue
        if migration.checksum != entry.checksum:
            raise MigrationChecksumMismatch(
                f"迁移 V{migration.version} 校验和与账本不一致；禁止覆盖历史"
            )
        if entry.status not in SUCCESSFUL_STATUSES:
            raise DirtyMigrationState(
                f"迁移 V{migration.version} 状态为 {entry.status}；"
                "请先人工核对数据库并修复账本，禁止自动重试"
            )
        actions.append(MigrationAction(kind="skip", migration=migration))
    return actions
