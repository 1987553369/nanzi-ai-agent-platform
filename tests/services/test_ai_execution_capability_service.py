"""AI 执行高风险控制的服务端 Capability 契约。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai_execution_capability_service import (
    AIExecutionCapabilityDenied,
    AUTO_APPROVE_TOOLS_CAPABILITY,
    DEBUG_PROMPT_CAPABILITY,
    resolve_ai_execution_controls,
)


pytestmark = pytest.mark.no_infrastructure


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("debug_options", "permission_options", "expected_capability"),
    [
        ({"return_raw_prompt": True}, None, DEBUG_PROMPT_CAPABILITY),
        ({"system_prompt_override": "Ignore policy"}, None, DEBUG_PROMPT_CAPABILITY),
        (None, {"approval_mode": "allow"}, AUTO_APPROVE_TOOLS_CAPABILITY),
    ],
)
async def test_unprivileged_user_cannot_enable_high_risk_controls(
    debug_options,
    permission_options,
    expected_capability,
):
    with patch(
        "app.services.ai_execution_capability_service._has_capability",
        AsyncMock(return_value=False),
    ):
        with pytest.raises(AIExecutionCapabilityDenied) as exc_info:
            await resolve_ai_execution_controls(
                AsyncMock(),
                {"user_id": 7, "role": "user"},
                debug_options=debug_options,
                permission_options=permission_options,
            )

    assert exc_info.value.capability == expected_capability


@pytest.mark.asyncio
async def test_granted_capabilities_allow_prompt_debug_and_auto_approval():
    checker = AsyncMock(return_value=True)
    with patch(
        "app.services.ai_execution_capability_service._has_capability",
        checker,
    ):
        debug, permissions = await resolve_ai_execution_controls(
            AsyncMock(),
            {"user_id": 7, "role": "user"},
            debug_options={
                "return_raw_prompt": True,
                "system_prompt_override": "Authorized override",
            },
            permission_options={"approval_mode": "allow", "untrusted": True},
        )

    assert debug == {
        "return_raw_prompt": True,
        "system_prompt_override": "Authorized override",
    }
    assert permissions == {"approval_mode": "allow"}
    assert [call.args[2] for call in checker.await_args_list] == [
        DEBUG_PROMPT_CAPABILITY,
        AUTO_APPROVE_TOOLS_CAPABILITY,
    ]


@pytest.mark.asyncio
async def test_admin_bypasses_capability_lookup():
    debug, permissions = await resolve_ai_execution_controls(
        AsyncMock(),
        {"user_id": 1, "role": "ADMIN"},
        debug_options={"return_raw_prompt": True},
        permission_options={"approval_mode": "allow"},
    )

    assert debug["return_raw_prompt"] is True
    assert permissions == {"approval_mode": "allow"}


@pytest.mark.asyncio
async def test_non_strict_runtime_downgrades_legacy_privileged_controls():
    with patch(
        "app.services.ai_execution_capability_service._has_capability",
        AsyncMock(return_value=False),
    ):
        debug, permissions = await resolve_ai_execution_controls(
            AsyncMock(),
            {"user_id": 7, "role": "user"},
            debug_options={
                "return_raw_prompt": True,
                "system_prompt_override": "legacy",
                "model": "deepseek-v3",
            },
            permission_options={"approval_mode": "allow"},
            reject_on_denied=False,
        )

    assert debug == {"model": "deepseek-v3"}
    assert permissions == {"approval_mode": "ask"}


@pytest.mark.asyncio
async def test_safe_controls_do_not_query_capabilities_and_strip_unknown_fields():
    checker = AsyncMock()
    with patch(
        "app.services.ai_execution_capability_service._has_capability",
        checker,
    ):
        debug, permissions = await resolve_ai_execution_controls(
            AsyncMock(),
            {"user_id": 7, "role": "user"},
            debug_options={"model": "deepseek-v3"},
            permission_options={"approval_mode": "deny", "auto_execute": True},
        )

    assert debug == {"model": "deepseek-v3"}
    assert permissions == {"approval_mode": "deny"}
    checker.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"debug_options": []}, "debug_options must be an object"),
        ({"permission_options": []}, "permission_options must be an object"),
        (
            {"debug_options": {"system_prompt_override": 1}},
            "system_prompt_override must be a string",
        ),
        (
            {"debug_options": {"system_prompt_override": "x" * 100_001}},
            "system_prompt_override is too long",
        ),
    ],
)
async def test_invalid_control_values_are_rejected(kwargs, message):
    with patch(
        "app.services.ai_execution_capability_service._has_capability",
        AsyncMock(return_value=True),
    ):
        with pytest.raises(ValueError, match=message):
            await resolve_ai_execution_controls(
                AsyncMock(),
                {"user_id": 1, "role": "admin"},
                **kwargs,
            )
