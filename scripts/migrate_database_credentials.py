"""Encrypt or quarantine saved external database passwords."""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core import database
from app.core.orm import AsyncSessionLocal
from app.models.db_connection import MetaDbConnectionConfig
from app.services.database_credential_migration import (
    migrate_database_credential_record,
)


@dataclass
class MigrationSummary:
    scanned: int = 0
    encrypted: int = 0
    verified: int = 0
    empty: int = 0
    migration_pending: int = 0
    rotation_required: int = 0


def parse_args(argv: Optional[Sequence[str]] = None):
    parser = argparse.ArgumentParser(
        description=(
            "Encrypt legacy external database passwords with the current "
            "ENCRYPTION_KEY. Dry-run is the default."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Persist changes")
    mode.add_argument("--dry-run", action="store_true", help="Inspect only (default)")
    parser.add_argument(
        "--config-id",
        action="append",
        type=int,
        default=[],
        help="Limit migration to one config ID; repeat for multiple IDs",
    )
    return parser.parse_args(argv)


async def migrate_one(config_id: int, *, apply: bool) -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MetaDbConnectionConfig)
            .where(MetaDbConnectionConfig.id == config_id)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return "missing"
        migration = migrate_database_credential_record(record, apply=apply)
        if apply:
            await session.commit()
        return migration.action


async def run_migration(
    *,
    apply: bool,
    config_ids: Sequence[int],
) -> MigrationSummary:
    await database.init_db()
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(MetaDbConnectionConfig.id).order_by(
                MetaDbConnectionConfig.created_at.asc()
            )
            if config_ids:
                stmt = stmt.where(
                    MetaDbConnectionConfig.id.in_(list(dict.fromkeys(config_ids)))
                )
            ids = list((await session.execute(stmt)).scalars().all())

        summary = MigrationSummary()
        for config_id in ids:
            summary.scanned += 1
            action = await migrate_one(config_id, apply=apply)
            if hasattr(summary, action):
                setattr(summary, action, getattr(summary, action) + 1)
        return summary
    finally:
        await database.close_db()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"Database credential migration mode: {mode}")
    summary = asyncio.run(
        run_migration(apply=apply, config_ids=args.config_id)
    )
    print(
        "Summary: "
        f"scanned={summary.scanned}, encrypted={summary.encrypted}, "
        f"verified={summary.verified}, empty={summary.empty}, "
        f"migration_pending={summary.migration_pending}, "
        f"rotation_required={summary.rotation_required}"
    )
    return 2 if summary.rotation_required or summary.migration_pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
