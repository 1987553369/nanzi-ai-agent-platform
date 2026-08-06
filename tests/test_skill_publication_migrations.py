from pathlib import Path
import re

import pytest


pytestmark = pytest.mark.no_infrastructure

REPO_ROOT = Path(__file__).resolve().parents[1]

PUBLICATION_COLUMNS = (
    "id",
    "platform_skill_id",
    "source_user_id",
    "source_personal_skill_id",
    "name",
    "description",
    "current_version",
    "status",
    "created_at",
    "updated_at",
    "revoked_at",
    "revoked_by",
)
VERSION_COLUMNS = (
    "id",
    "publication_id",
    "version_number",
    "status",
    "snapshot_path",
    "content_sha256",
    "file_count",
    "total_size",
    "submitted_by",
    "submitted_at",
    "reviewed_by",
    "reviewed_at",
    "review_comment",
    "published_at",
    "materialized_path",
    "withdrawn_by",
    "withdrawn_at",
)


def test_mysql_skill_publication_migration_has_table_and_column_comments():
    sql = (REPO_ROOT / "db-prod/V111.1-create-skill-publications.sql").read_text()

    assert "COMMENT='个人技能发布到平台公共技能库的发布谱系'" in sql
    assert "COMMENT='个人技能平台发布的候选与审核版本'" in sql
    for column in PUBLICATION_COLUMNS + VERSION_COLUMNS:
        assert re.search(rf"\b{re.escape(column)}\b\s+[^,\n]+COMMENT\s+'", sql)


def test_postgres_skill_publication_migration_has_table_and_column_comments():
    sql = (REPO_ROOT / "db-prod-pg/V10-create-skill-publications.sql").read_text()

    assert 'COMMENT ON TABLE "skill_publications" IS' in sql
    assert 'COMMENT ON TABLE "skill_publication_versions" IS' in sql
    for table, columns in (
        ("skill_publications", PUBLICATION_COLUMNS),
        ("skill_publication_versions", VERSION_COLUMNS),
    ):
        for column in columns:
            assert f'COMMENT ON COLUMN "{table}"."{column}" IS' in sql


def test_mysql_withdrawal_migration_backfills_existing_publication_versions():
    sql = (REPO_ROOT / "db-prod/V112-add-skill-publication-withdrawal.sql").read_text()

    assert "withdrawn_by" in sql
    assert "withdrawn_at" in sql
    assert "ALTER TABLE skill_publication_versions" in sql
    assert "ADD COLUMN withdrawn_by BIGINT" in sql
    assert "ADD COLUMN withdrawn_at DATETIME" in sql


def test_postgres_withdrawal_migration_backfills_existing_publication_versions():
    sql = (REPO_ROOT / "db-prod-pg/V11-add-skill-publication-withdrawal.sql").read_text()

    assert 'ADD COLUMN IF NOT EXISTS "withdrawn_by" BIGINT' in sql
    assert 'ADD COLUMN IF NOT EXISTS "withdrawn_at" TIMESTAMP' in sql
    assert 'COMMENT ON COLUMN "skill_publication_versions"."withdrawn_by"' in sql
    assert 'COMMENT ON COLUMN "skill_publication_versions"."withdrawn_at"' in sql
