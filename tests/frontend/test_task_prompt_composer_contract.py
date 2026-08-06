"""Contract: TaskCenter prompt composer supports model/approval/resource scope."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK_CENTER = ROOT / "frontend" / "src" / "views" / "TaskCenter.vue"
COMPOSER = ROOT / "frontend" / "src" / "components" / "task" / "TaskPromptComposer.vue"
SCHEDULER = ROOT / "app" / "services" / "ai" / "scheduler_service.py"
OPTIONS = ROOT / "app" / "services" / "task_execution_options.py"


def test_task_prompt_composer_exposes_model_approval_and_resources():
    text = COMPOSER.read_text(encoding="utf-8")
    assert "自动批准" in text
    assert "请求批准" in text
    assert "定时任务无法弹窗审批" in text
    assert "datasets" in text
    assert "knowledge_bases" in text
    assert "skills" in text
    assert "mcp_tools" in text
    assert "默认模型" in text or "智能体默认模型" in text
    # 技能：平台 / 个人 Tab，对齐 EmbedChat
    assert "skillScopeTab" in text
    assert "平台" in text
    assert "我的" in text
    assert "skillScopeSelectedCount" in text
    # MCP：按服务分组、默认折叠、组内全选；仅个人已发布
    assert "mcpGroupsForActiveOptions" in text
    assert "collapsedMcpGroups" in text
    assert "toggleMcpGroupSelectAll" in text
    assert "取消全选" in text
    assert "mcpToolDisplayName" in text
    assert "=== 'personal'" in text or '=== "personal"' in text or "=== 'personal'" in text
    assert "仅可挂载个人已发布 MCP" in text


def test_task_prompt_composer_panels_escape_modal_clipping():
    """任务弹窗正文与组件根节点都有 overflow 裁剪，浮层必须挂到 body 用 fixed 定位。"""
    text = COMPOSER.read_text(encoding="utf-8")
    assert "<Teleport to=\"body\">" in text
    # 面板不能再用相对父容器的绝对定位，否则会被裁掉
    assert "absolute bottom-full" not in text
    assert "panelStyle" in text
    assert "getBoundingClientRect" in text
    # 需要跟随滚动/缩放重算位置，capture=true 才能捕获弹窗正文的滚动
    assert "'scroll', onViewportChange, true" in text
    assert "'resize', onViewportChange" in text
    # 浮层已脱离根节点，点击判定必须同时认面板自身
    assert "panelRef.value?.contains(target)" in text


def test_task_prompt_composer_panels_can_be_dismissed():
    """三个浮层都要能关掉：点外部 / 指针移开 / 关闭按钮 / Esc。"""
    text = COMPOSER.read_text(encoding="utf-8")
    # 「外部」按按钮栏判定，点文本框、已选标签、说明文字都应收起面板
    assert "barRef.value?.contains(target)" in text
    assert "rootRef" not in text
    # 指针移开延时关闭，进入面板或按钮栏时取消
    assert text.count("@pointerleave=\"scheduleClose\"") == 4
    assert text.count("@pointerenter=\"cancelPendingClose\"") == 4
    # 三个面板各自带标题与关闭按钮
    assert text.count("@click=\"closePanel\"") == 3
    assert text.count("{{ panelTitle }}") == 3
    assert "'Escape'" in text
    # 触摸设备抬手即 pointerleave，自动关闭只能对鼠标生效
    assert "event.pointerType !== 'mouse'" in text


def test_task_center_wires_prompt_composer_into_config():
    text = TASK_CENTER.read_text(encoding="utf-8")
    assert "TaskPromptComposer" in text
    assert "approval_mode" in text
    assert "resource_scope" in text
    assert "taskModel" in text
    assert "hydrateExecutionOptions" in text
    assert 'element:chat:auto_approve_tools' in text
    assert ':can-auto-approve="canAutoApproveTools"' in text


def test_scheduler_reads_task_execution_options_from_config():
    scheduler = SCHEDULER.read_text(encoding="utf-8")
    options = OPTIONS.read_text(encoding="utf-8")
    assert "permission_options_from_task_config" in scheduler
    assert "debug_options_from_task_config" in scheduler
    assert "knowledge_dataset_ids" in scheduler
    assert "metadata_dataset_ids" in scheduler
    assert "DEFAULT_APPROVAL_MODE = \"ask\"" in options
    assert "resource_scope" in options


def test_auto_approval_is_hidden_without_server_capability():
    composer = COMPOSER.read_text(encoding="utf-8")
    assert "canAutoApprove" in composer
    assert "availableApprovalOptions" in composer
    assert "mode === 'allow' && !props.canAutoApprove" in composer
