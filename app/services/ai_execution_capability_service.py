"""Server-side authorization for AI execution controls supplied by clients."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.task_execution_options import normalize_approval_mode


logger = logging.getLogger(__name__)

DEBUG_PROMPT_CAPABILITY = "element:chat:debug_prompt"
AUTO_APPROVE_TOOLS_CAPABILITY = "element:chat:auto_approve_tools"
PRIVILEGED_DEBUG_KEYS = frozenset({"return_raw_prompt", "system_prompt_override"})


class AIExecutionCapabilityDenied(PermissionError):
    def __init__(self, capability: str):
        super().__init__(f"AI execution capability required: {capability}")
        self.capability = capability


async def _has_capability(
    db: AsyncSession,
    user_info: Mapping[str, Any],
    capability: str,
) -> bool:
    if str(user_info.get("role") or "").lower() == "admin":
        return True
    try:
        user_id = int(user_info.get("user_id") or user_info.get("id"))
    except (TypeError, ValueError):
        return False
    from app.services.permission_service import PermissionService

    return await PermissionService(db).check_permission(
        user_id,
        "element",
        capability,
    )


def _privileged_debug_requested(options: Mapping[str, Any]) -> bool:
    return bool(
        options.get("return_raw_prompt")
        or options.get("system_prompt_override")
    )


async def resolve_ai_execution_controls(
    db: AsyncSession,
    user_info: Mapping[str, Any],
    *,
    debug_options: Optional[Mapping[str, Any]] = None,
    permission_options: Optional[Mapping[str, Any]] = None,
    reject_on_denied: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Authorize prompt debugging and tool auto-approval at the server boundary."""
    if debug_options is not None and not isinstance(debug_options, Mapping):
        raise ValueError("debug_options must be an object")
    if permission_options is not None and not isinstance(permission_options, Mapping):
        raise ValueError("permission_options must be an object")

    effective_debug = dict(debug_options or {})
    user_id = str(user_info.get("user_id") or user_info.get("id") or "unknown")

    if _privileged_debug_requested(effective_debug):
        allowed = await _has_capability(db, user_info, DEBUG_PROMPT_CAPABILITY)
        if not allowed:
            logger.warning(
                "Denied privileged AI debug controls: user_id=%s capability=%s",
                user_id,
                DEBUG_PROMPT_CAPABILITY,
            )
            if reject_on_denied:
                raise AIExecutionCapabilityDenied(DEBUG_PROMPT_CAPABILITY)
            for key in PRIVILEGED_DEBUG_KEYS:
                effective_debug.pop(key, None)

    prompt_override = effective_debug.get("system_prompt_override")
    if prompt_override is not None:
        if not isinstance(prompt_override, str):
            raise ValueError("system_prompt_override must be a string")
        if len(prompt_override) > 100_000:
            raise ValueError("system_prompt_override is too long")

    requested_mode = normalize_approval_mode(
        (permission_options or {}).get("approval_mode"),
        default="ask",
    )
    if requested_mode == "allow":
        allowed = await _has_capability(db, user_info, AUTO_APPROVE_TOOLS_CAPABILITY)
        if not allowed:
            logger.warning(
                "Denied tool auto-approval: user_id=%s capability=%s",
                user_id,
                AUTO_APPROVE_TOOLS_CAPABILITY,
            )
            if reject_on_denied:
                raise AIExecutionCapabilityDenied(AUTO_APPROVE_TOOLS_CAPABILITY)
            requested_mode = "ask"

    return effective_debug, {"approval_mode": requested_mode}
