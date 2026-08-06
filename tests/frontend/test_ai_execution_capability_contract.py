"""前端高风险 AI 执行控件必须与服务端 Capability 对齐。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT_INPUT = ROOT / "frontend" / "src" / "components" / "embed" / "ChatInput.vue"
DEBUG_PANEL = ROOT / "frontend" / "src" / "components" / "DebugConfigPanel.vue"
AGENT_DEBUG = ROOT / "frontend" / "src" / "views" / "AgentDebug.vue"


def test_chat_auto_approval_requires_capability():
    source = CHAT_INPUT.read_text(encoding="utf-8")
    assert "element:chat:auto_approve_tools" in source
    assert "availableApprovalModeOptions" in source
    assert 'mode === "allow" && !canAutoApproveTools.value' in source


def test_prompt_debug_controls_require_capability():
    debug = AGENT_DEBUG.read_text(encoding="utf-8")
    panel = DEBUG_PANEL.read_text(encoding="utf-8")
    assert "element:chat:debug_prompt" in debug
    assert ':can-debug-prompt="canDebugPrompt"' in debug
    assert "canDebugPrompt.value && debugConfig.returnRawPrompt" in debug
    assert "canDebugPrompt.value && debugConfig.systemPromptOverride.trim()" in debug
    assert panel.count('v-if="canDebugPrompt"') >= 2
