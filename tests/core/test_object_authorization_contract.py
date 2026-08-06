from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_portal_trace_endpoints_require_history_owner_access():
    source = _source("app/api/portal/endpoints/audit.py")

    assert source.count("await _require_trace_access(trace_id, user, db)") >= 2
    assert "AgentExecutionHistory.trace_id == trace_id" in source
    assert "owner_user_id == current_user_id" in source
    assert "owner_username == current_username" in source


def test_active_agent_config_requires_agent_execute_access():
    source = _source("app/api/portal/endpoints/agents.py")

    assert source.count("AgentManagerService._user_can_execute_agent") >= 3
    assert "无权查看该智能体的活跃配置" in source
    assert "无权查看该智能体的欢迎配置" in source


def test_mcp_tool_execution_uses_distributed_rate_limit():
    source = _source("app/api/portal/endpoints/mcp.py")

    assert 'bucket="mcp-tool-execution"' in source
    assert "settings.TOOL_EXECUTION_RATE_LIMIT" in source
