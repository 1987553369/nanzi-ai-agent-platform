from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.agent_service import AgentService
pytestmark = pytest.mark.no_infrastructure

@pytest.mark.asyncio
async def test_ltm_applied_in_stream_meta():
    """LTM 加载后返回可注入 meta 的 profile 和原始数据。"""
    agent_service = AgentService()
    mock_ltm_data = {
        "user_preferred_city": "临港",
        "work_style": "premium"
    }
    with patch("app.services.ai.turn_classifier.should_inject_ltm", return_value=True), \
         patch("app.services.ai.turn_classifier.should_inject_memory_recall_hint", return_value=False), \
         patch("app.services.ai.turn_classifier.should_run_active_memory_preload", return_value=False), \
         patch("app.services.ai.memory_service.ltm_service.fetch_memory", new_callable=AsyncMock, return_value=mock_ltm_data), \
         patch("app.services.ai.agent_service.logger"):
        profile, loaded_data, recall_hint, preloaded = await agent_service._load_memory_context(
            user_info={"user_id": "test_user_99"},
            early_turn_type=MagicMock(),
            debug_options=None,
            user_query="你好",
        )

    assert profile is not None
    assert "临港" in profile
    assert loaded_data == mock_ltm_data
    assert recall_hint is None
    assert preloaded is None


@pytest.mark.asyncio
async def test_ignore_ltm_in_stream_meta():
    """ignore_ltm=True 时不读取 LTM。"""
    agent_service = AgentService()
    with patch("app.services.ai.turn_classifier.should_inject_ltm", return_value=True), \
         patch("app.services.ai.turn_classifier.should_inject_memory_recall_hint", return_value=False), \
         patch("app.services.ai.turn_classifier.should_run_active_memory_preload", return_value=False), \
         patch("app.services.ai.memory_service.ltm_service.fetch_memory", new_callable=AsyncMock) as mock_fetch_memory, \
         patch("app.services.ai.agent_service.logger"):
        profile, loaded_data, recall_hint, preloaded = await agent_service._load_memory_context(
            user_info={"user_id": "test_user_99"},
            early_turn_type=MagicMock(),
            debug_options={"ignore_ltm": True},
            user_query="你好",
        )

    assert profile is None
    assert loaded_data is None
    assert recall_hint is None
    assert preloaded is None
    mock_fetch_memory.assert_not_called()
