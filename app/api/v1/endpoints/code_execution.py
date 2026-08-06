from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.dependencies import require_api_key
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.services.ai.code_execution_service import (
    CodeExecutionValidationError,
    get_execution,
    normalize_language,
    register_execution,
    start_code_execution,
    unregister_execution,
)
from app.services.ai.runtime.workspace_access_policy import (
    WorkspaceAccessDenied,
    ensure_private_workspace_dirs,
    user_workspace_root,
    validate_execution_workspace,
)


router = APIRouter()


class CodeExecutionRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=32)
    code: str = Field(..., min_length=1, max_length=1024 * 1024)
    conversation_id: str = Field(..., min_length=1, max_length=200)


class CodeExecutionStopRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=200)


async def resolve_execution_workspace(
    *,
    user_info: dict[str, Any],
    conversation_id: str,
    root: str | None = None,
) -> str:
    from app.services.ai.runtime.agentscope.workspace import (
        resolve_session_workdir,
        resolve_workspace_root,
    )

    user_id = user_info.get("user_id") or user_info.get("id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="无法解析当前用户。")
    workspace_root = root or await resolve_workspace_root()
    workspace = resolve_session_workdir(
        root=workspace_root,
        user_id=user_id,
        user_name=user_info.get("user_name") or user_info.get("username"),
        user_info=user_info,
        conversation_id=conversation_id,
    )
    try:
        validated = validate_execution_workspace(
            workspace,
            workspace_root=workspace_root,
            user_info=user_info,
        )
        ensure_private_workspace_dirs(
            user_workspace_root(workspace_root, user_info),
            validated,
        )
    except WorkspaceAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return str(validated)


def _sse_event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream", summary="运行聊天中的代码块")
async def stream_code_execution(
    body: CodeExecutionRequest,
    request: Request,
    user_info: dict[str, Any] = Depends(require_api_key),
):
    await enforce_rate_limit(
        bucket="code-execution",
        identifier=str(user_info.get("user_id") or user_info.get("id") or "unknown"),
        limit=settings.CODE_EXECUTION_RATE_LIMIT,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="代码不能为空。")
    try:
        language = normalize_language(body.language)
    except CodeExecutionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.services.ai.runtime.agentscope.workspace import resolve_workspace_root

    workspace_root = await resolve_workspace_root()
    workspace = await resolve_execution_workspace(
        user_info=user_info,
        conversation_id=body.conversation_id,
        root=workspace_root,
    )
    handle = start_code_execution(
        language=language,
        code=body.code,
        workspace=workspace,
        workspace_root=workspace_root,
        user_info=user_info,
        conversation_id=body.conversation_id,
    )
    register_execution(handle)

    async def sse_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in handle.events():
                if await request.is_disconnected():
                    await handle.stop()
                    break
                yield _sse_event(event.name, event.data)
        except Exception as exc:
            yield _sse_event("error", {"code": "stream_error", "message": str(exc)})
        finally:
            task = getattr(handle, "_task", None)
            if task is not None and not task.done():
                await handle.stop()
            unregister_execution(handle)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/{execution_id}/stop", summary="停止代码执行")
async def stop_code_execution(
    execution_id: str,
    body: CodeExecutionStopRequest,
    user_info: dict[str, Any] = Depends(require_api_key),
):
    handle = get_execution(execution_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="执行实例不存在或已结束。")

    user_id = user_info.get("user_id") or user_info.get("id")
    if str(handle.user_id) != str(user_id) or handle.conversation_id != body.conversation_id:
        raise HTTPException(status_code=403, detail="无权停止该执行实例。")

    stopped = await handle.stop()
    return {
        "execution_id": execution_id,
        "status": "stopping" if stopped else "finished",
    }
