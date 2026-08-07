from pathlib import Path

import pytest

from app.schemas.db_connection import DbConnectionConfigSafeResponse


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_database_config_response_never_contains_password():
    fields = DbConnectionConfigSafeResponse.model_fields

    assert "password" not in fields
    assert "has_password" in fields
    assert "credential_status" in fields


def test_frontend_never_reads_saved_database_password():
    api = _source("frontend/src/api/metadata.ts")
    management = _source("frontend/src/views/DataSourceManagement.vue")
    importer = _source("frontend/src/components/metadata/DatabaseImportModal.vue")

    assert "password: string;" not in api
    assert "item.password" not in management
    assert "c.password" not in importer
    assert "testSavedDbConnection" in management
    assert "listSavedDbTables" in importer
    assert "getSavedDbDdl" in importer
    assert "已配置；留空保留原密码" in management
    assert "连接目标已变化，请重新输入密码" in management


def test_saved_config_api_decrypts_only_on_the_server():
    endpoint = _source("app/api/portal/endpoints/metadata.py")
    service = _source("app/services/db_connection_service.py")

    assert '"/db/connection-configs/{config_id}/test"' in endpoint
    assert '"/db/connection-configs/{config_id}/tables"' in endpoint
    assert '"/db/connection-configs/{config_id}/ddl"' in endpoint
    assert "DbConnectionService.to_runtime_config(config)" in endpoint
    assert "decrypt_database_password(" in service
    assert "return str(config.password" not in service


def test_runtime_consumers_use_central_decryption_and_pool_rotation():
    pool = _source("app/services/pool_manager.py")
    profile = _source("app/services/db_profile_service.py")
    endpoint = _source("app/api/portal/endpoints/metadata.py")

    assert pool.count("DbConnectionService.get_runtime_password(db_config)") >= 6
    assert profile.count("DbConnectionService.to_runtime_config(config)") == 2
    assert "await DataSourcePoolManager.invalidate_pool(config_id)" in endpoint
