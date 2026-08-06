from pathlib import Path

import pytest

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _build_settings(**overrides):
    values = {
        "_env_file": None,
        "DATABASE_TYPE": "mysql",
        "MYSQL_HOST": "localhost",
        "MYSQL_DB": "nanzi_ai_agent_platform",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "secret",
        "POSTGRES_HOST": "pg.local",
        "POSTGRES_PORT": 5432,
        "POSTGRES_DB": "nanzi_ai_agent_platform",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "secret",
        "REDIS_HOST": "localhost",
        "ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    values.update(overrides)
    return Settings(**values)


def test_database_type_defaults_to_mysql_when_not_configured():
    settings = _build_settings()

    assert settings.DATABASE_TYPE == "mysql"


def test_runtime_defaults_do_not_contain_credentials_and_log_level_is_configurable():
    settings = _build_settings(LOG_LEVEL="warning")

    assert settings.SSO_ACCESS_TOKEN == "CHANGE_ME_SSO_ACCESS_TOKEN"
    assert settings.LOG_LEVEL == "warning"


def test_production_rejects_placeholder_security_configuration():
    settings = _build_settings(
        API_SERVICE_ENV="production",
        ENCRYPTION_KEY="GENERATE_A_UNIQUE_FERNET_KEY",
        SSO_ACCESS_TOKEN="CHANGE_ME_SSO_ACCESS_TOKEN",
    )

    with pytest.raises(ValueError, match="生产环境禁止使用占位安全配置"):
        settings.validate_runtime_configuration()


def test_development_allows_local_placeholder_configuration():
    settings = _build_settings(
        API_SERVICE_ENV="dev",
        ENCRYPTION_KEY="GENERATE_A_UNIQUE_FERNET_KEY",
        SSO_ACCESS_TOKEN="CHANGE_ME_SSO_ACCESS_TOKEN",
    )

    settings.validate_runtime_configuration()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SSO_API_URL": "http://sso.example.com/login"}, "SSO_API_URL 必须使用 HTTPS"),
        ({"ALLOWED_ORIGINS": ["*"]}, "ALLOWED_ORIGINS 禁止使用通配符"),
    ],
)
def test_production_rejects_insecure_network_configuration(overrides, message):
    settings = _build_settings(
        API_SERVICE_ENV="production",
        SSO_ACCESS_TOKEN="production-sso-token",
        **overrides,
    )

    with pytest.raises(ValueError, match=message):
        settings.validate_runtime_configuration()


def test_cors_defaults_to_same_origin_only():
    settings = _build_settings()

    assert settings.ALLOWED_ORIGINS == []


def test_database_type_accepts_postgresql_override():
    settings = _build_settings(DATABASE_TYPE="postgresql")

    assert settings.DATABASE_TYPE == "postgresql"


def test_database_urls_use_database_type_specific_async_and_sync_drivers():
    mysql = _build_settings()
    assert mysql.DATABASE_ASYNC_URL.drivername == "mysql+aiomysql"
    assert mysql.DATABASE_SYNC_URL.startswith("mysql+pymysql://")

    postgresql = _build_settings(DATABASE_TYPE="postgresql")
    assert postgresql.DATABASE_ASYNC_URL.drivername == "postgresql+psycopg"
    assert postgresql.DATABASE_SYNC_URL.startswith("postgresql+psycopg://")


@pytest.mark.parametrize("database_type", ["postgres", "pg", "POSTGRESQL"])
def test_database_type_accepts_postgresql_aliases(database_type):
    settings = _build_settings(DATABASE_TYPE=database_type)

    assert settings.DATABASE_ASYNC_URL.drivername == "postgresql+psycopg"


def test_database_type_rejects_unknown_values():
    settings = _build_settings(DATABASE_TYPE="oracle")

    with pytest.raises(ValueError, match="Unsupported DATABASE_TYPE"):
        _ = settings.DATABASE_ASYNC_URL


def test_postgresql_settings_do_not_require_mysql_fields():
    values = {
        "_env_file": None,
        "DATABASE_TYPE": "postgresql",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "nanzi_ai_agent_platform",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "secret",
        "REDIS_HOST": "localhost",
        "ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }

    settings = Settings(**values)

    assert settings.DATABASE_ASYNC_URL.drivername == "postgresql+psycopg"


def test_mysql_url_reports_missing_selected_fields():
    settings = _build_settings(MYSQL_HOST=None, MYSQL_DB=None, MYSQL_USER=None, MYSQL_PASSWORD=None)

    with pytest.raises(ValueError, match="MySQL database configuration is incomplete"):
        _ = settings.DATABASE_ASYNC_URL


def test_environment_files_document_mysql_default_database_type():
    assert "DATABASE_TYPE=mysql" in (ROOT / "env.example").read_text(encoding="utf-8")
    dotenv = ROOT / ".env"
    if dotenv.exists():
        assert "DATABASE_TYPE=" in dotenv.read_text(encoding="utf-8")


def test_wait_for_services_selects_the_configured_database():
    script = (ROOT / "scripts/wait-for-services.sh").read_text(encoding="utf-8")

    assert 'database_type="${DATABASE_TYPE:-mysql}"' in script
    assert 'database_host="${POSTGRES_HOST:-localhost}"' in script
    assert 'database_port="${POSTGRES_PORT:-5432}"' in script
