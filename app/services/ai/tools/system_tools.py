import logging
import json
import pytz
from datetime import datetime
from app.services.ai.tools.tool_compat import tool
from app.services.ai.tools.task_manager_tools import (
    create_recurring_task, get_my_tasks, cancel_task, 
    start_task, pause_task, run_task_manually
)
from app.services.ai.tools.notification_tools import send_dingtalk_message
from app.utils.outbound_url_policy import (
    create_ssrf_safe_async_client,
    redact_outbound_url_for_log,
    validate_outbound_http_url,
)

logger = logging.getLogger(__name__)


@tool
def get_current_model() -> str:
    """查询本轮实际生效的模型身份和调用阶段，不返回凭据或服务地址。"""
    from app.core.context import get_current_agent_context

    context = get_current_agent_context()
    info = dict(getattr(context, "runtime_model_info", {}) or {}) if context else {}
    if not info:
        return json.dumps(
            {
                "status": "unavailable",
                "reason": "当前请求没有可用的运行时模型信息",
            },
            ensure_ascii=False,
        )
    return json.dumps(info, ensure_ascii=False)

def validate_url(url: str) -> bool:
    """Compatibility preflight; DNS enforcement happens in the pinned transport."""
    validate_outbound_http_url(url)
    return True

@tool
async def system_http_request(method: str, url: str, headers: dict = None, body: dict = None, params: dict = None) -> str:
    """
    Executes a generic HTTP request to an external API.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        url: The full URL to request.
        headers: Optional dictionary of HTTP headers.
        body: Optional dictionary for JSON body (for POST/PUT).
        params: Optional dictionary for Query parameters.
    """
    try:
        # Security Check
        validate_url(url)
        
        method = method.upper()
        if headers is None:
            headers = {}
        # Set a default User-Agent if not present
        if "User-Agent" not in headers and "user-agent" not in headers:
            headers["User-Agent"] = "NanZi-AI-Agent/1.0"

        timeout = 30.0
        
        async with create_ssrf_safe_async_client(
            allowed_url=url,
            timeout=timeout,
        ) as client:
            logger.info(
                "[SystemTool] %s %s parameter_keys=%s",
                method,
                redact_outbound_url_for_log(url),
                sorted((params or {}).keys()),
            )
            
            if method == "GET":
                response = await client.get(url, params=params, headers=headers)
            elif method in ["POST", "PUT", "PATCH", "DELETE"]:
                response = await client.request(method, url, json=body, params=params, headers=headers)
            else:
                return f"Error: Unsupported method {method}"

            # Try to return JSON if possible, else text
            try:
                data = response.json()
                return json.dumps(data, ensure_ascii=False)
            except:
                return response.text[:10000] # Truncate generic text responses to avoid context overflow

    except Exception as e:
        return f"Error executing request: {str(e)}"

@tool
def resolve_relative_dates(phrases: list[str], timezone: str = "") -> str:
    """
    将中文相对日期短语解析为具体起止日期（YYYY-MM-DD），与系统【当前时间锚点】同源。

    使用规则：
    - 若 system prompt 已含【当前时间锚点】或【本轮问题时间解读】，优先直接引用，勿重复调用。
    - 仅当需要解析锚点未覆盖的短语时调用；每轮用户问题最多调用 1 次。
    - phrases: 如 ["近7天", "上周", "下周五"]，可一次传入多个。

    Args:
        phrases: 相对日期短语列表。
        timezone: IANA 时区；留空则使用平台系统配置 platform_timezone。
    """
    from app.services.ai.time_anchor import resolve_relative_date_phrases
    from app.services.platform_timezone import get_cached_platform_timezone

    rows = resolve_relative_date_phrases(
        phrases,
        timezone=(timezone or "").strip() or get_cached_platform_timezone(),
    )
    return json.dumps(rows, ensure_ascii=False)


@tool
def get_current_time(timezone: str = "") -> str:
    """
    获取当前系统时间（含星期）。

    使用规则：
    - 问候语（你好/在吗）禁止调用。
    - 若 system prompt 已含【当前时间锚点】，相对时间（今天/近N天/本周等）须直接用锚点日期，禁止为换算日期反复调用本工具。
    - 每轮用户问题最多调用 1 次；仅当锚点缺失且必须知道「此刻」时再调用。

    Args:
        timezone: IANA 时区（如 UTC、Asia/Shanghai）；留空则使用平台系统配置 platform_timezone。
    """
    try:
        from app.services.platform_timezone import get_cached_platform_timezone

        tz_name = (timezone or "").strip() or get_cached_platform_timezone()
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        
        # Add Chinese weekday
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[now.weekday()]
        
        return now.strftime(f"%Y-%m-%d %H:%M:%S {weekday_str} %Z%z")
    except Exception as e:
        return f"Error getting time: {str(e)}"


SYSTEM_IMPLICIT_TOOLS = [
    get_current_model,
    get_current_time,
    resolve_relative_dates,
    create_recurring_task,
    get_my_tasks,
    cancel_task,
    start_task,
    pause_task,
    run_task_manually,
]
