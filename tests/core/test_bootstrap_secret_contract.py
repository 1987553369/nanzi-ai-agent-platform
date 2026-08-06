from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_bootstrap_contains_no_fixed_api_key_or_ciphertext():
    files = [
        "db-prod/INIT-USER-ADMIN.sql",
        "db-prod/apply-sql.sh",
        "db-prod/apply-sql-native.sh",
    ]
    combined = "\n".join(_source(path) for path in files)

    assert "Z0FBQUFBQ" not in combined
    assert "INSERT INTO ai_agent_users" not in _source("db-prod/INIT-USER-ADMIN.sql")
    assert "scripts/create_admin_user.py" in _source("db-prod/apply-sql.sh")


def test_example_environments_require_unique_secrets():
    combined = "\n".join(
        _source(path)
        for path in (
            "env.example",
            "docker/env.example",
            "docker/docker-compose.yml",
            "docker/docker-compose.ai-agent.yml",
            "app/core/config.py",
        )
    )

    assert "root123" not in combined
    assert "laplace" not in combined
    assert "GENERATE_A_UNIQUE_FERNET_KEY" in combined
    assert "CHANGE_ME_SSO_ACCESS_TOKEN" in combined


def test_compose_requires_database_redis_and_encryption_secrets():
    compose = _source("docker/docker-compose.yml")
    external_compose = _source("docker/docker-compose.ai-agent.yml")
    for source in (compose, external_compose):
        assert "MYSQL_PASSWORD:?MYSQL_PASSWORD must be set" in source
        assert "REDIS_PASSWORD:?REDIS_PASSWORD must be set" in source
        assert "ENCRYPTION_KEY:?ENCRYPTION_KEY must be set" in source

    assert "service_healthy" in compose
    assert "--appendonly" in compose
