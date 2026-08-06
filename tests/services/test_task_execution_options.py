from app.services.task_execution_options import (
    debug_options_from_task_config,
    knowledge_dataset_ids_from_scope,
    merge_execution_options_into_config,
    metadata_dataset_ids_from_scope,
    normalize_approval_mode,
    permission_options_from_task_config,
    resource_scope_from_task_config,
)


def test_normalize_approval_mode_defaults_to_ask():
    assert normalize_approval_mode(None) == "ask"
    assert normalize_approval_mode("ASK") == "ask"
    assert normalize_approval_mode("bogus") == "ask"


def test_permission_options_from_task_config():
    assert permission_options_from_task_config({}) == {"approval_mode": "ask"}
    assert permission_options_from_task_config({"approval_mode": "ask"}) == {"approval_mode": "ask"}


def test_resource_scope_and_dataset_ids_from_task_config():
    config = {
        "model": "deepseek-v3",
        "resource_scope": {
            "datasets": [{"id": "ds1", "name": "销售库"}],
            "knowledge_bases": [{"id": "kb1", "name": "制度库"}],
            "skills": [{"id": "skill-a", "name": "巡检", "scope": "personal"}],
            "mcp_tools": [{"id": "t1", "name": "search_x", "scope": "personal"}],
        },
    }
    scope = resource_scope_from_task_config(config)
    assert scope["datasets"][0]["id"] == "ds1"
    assert scope["skills"][0]["scope"] == "personal"
    assert knowledge_dataset_ids_from_scope(scope) == ["kb1"]
    assert metadata_dataset_ids_from_scope(scope) == ["ds1"]
    debug = debug_options_from_task_config(config)
    assert debug["model"] == "deepseek-v3"
    assert debug["resource_scope"]["mcp_tools"][0]["name"] == "search_x"


def test_merge_execution_options_into_config_clears_empty_scope():
    merged = merge_execution_options_into_config(
        {"notification_channels": ["portal"], "resource_scope": {"datasets": [{"id": "x", "name": "x"}]}},
        approval_mode="allow",
        model="",
        resource_scope={"datasets": [], "knowledge_bases": [], "skills": [], "mcp_tools": []},
    )
    assert merged["approval_mode"] == "allow"
    assert "model" not in merged
    assert "resource_scope" not in merged
    assert merged["notification_channels"] == ["portal"]
