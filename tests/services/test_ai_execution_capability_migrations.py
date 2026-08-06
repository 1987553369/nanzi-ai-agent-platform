"""MySQL/PostgreSQL 高风险 AI Capability 注册迁移契约。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MYSQL_MIGRATION = ROOT / "db-prod" / "V116-register_ai_execution_capabilities.sql"
POSTGRES_MIGRATION = ROOT / "db-prod-pg" / "V15-register_ai_execution_capabilities.sql"


def test_capability_migrations_are_idempotent_and_do_not_grant_permissions():
    for path in (MYSQL_MIGRATION, POSTGRES_MIGRATION):
        source = path.read_text(encoding="utf-8")
        assert "element:chat:debug_prompt" in source
        assert "element:chat:auto_approve_tools" in source
        assert "WHERE NOT EXISTS" in source
        assert "user_id" not in source
        assert "role_id" not in source

    assert "INSERT IGNORE" not in MYSQL_MIGRATION.read_text(encoding="utf-8")
