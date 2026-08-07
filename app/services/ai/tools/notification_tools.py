import logging
from typing import Any, Dict, Optional, Type
from app.services.ai.tools.tool_compat import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class DingTalkInput(BaseModel):
    title: str = Field(description="The title of the message (visible in notifications)")
    content: str = Field(description="The main body of the message in Markdown format")

class send_dingtalk_message(BaseTool):
    # Pydantic v2 requires type annotations for field overrides
    name: str = "send_dingtalk_message"
    description: str = (
        "发送钉钉群机器人 Markdown 消息。Send a Markdown message to DingTalk. "
        "本工具会自动读取当前用户在个人中心 -> 消息通知里的钉钉 Webhook/加签配置，"
        "无需用户在本轮对话中提供 webhook、access_token 或群聊目标。"
    )
    args_schema: Type[BaseModel] = DingTalkInput

    async def _arun(self, title: str, content: str) -> str:
        """Use the tool asynchronously."""
        from app.core.context import get_current_agent_context
        from app.core.orm import AsyncSessionLocal
        from app.services.notification_service import NotificationService

        agent_ctx = get_current_agent_context()
        if not agent_ctx or not agent_ctx.user_id:
            return "Error: DingTalk Webhook URL not configured. Please go to Personal Center -> Message Notifications and set it."

        try:
            async with AsyncSessionLocal() as db:
                success, error = await NotificationService.send_dingtalk(
                    db,
                    agent_ctx.user_id,
                    title,
                    content,
                )
            if success:
                return f"Successfully sent DingTalk message: {title}"
            return f"Failed to send DingTalk message: {error}"
        except Exception as e:
            logger.error(f"DingTalk Tool Error: {e}", exc_info=True)
            return f"Error executing DingTalk tool: {str(e)}"

    def _run(self, title: str, content: str) -> str:
        raise NotImplementedError("Use _arun instead")

class EmailInput(BaseModel):
    to_email: str = Field(description="The recipient email address (e.g. 'user@example.com')")
    subject: str = Field(description="The subject line of the email")
    content: str = Field(description="The body content of the email (Markdown or Text)")

class send_email(BaseTool):
    name: str = "send_email"
    description: str = (
        "发送邮件通知。Send an email via SMTP. "
        "本工具会自动读取当前用户在个人中心 -> 消息通知里的 SMTP 配置，"
        "无需用户在本轮对话中提供 SMTP 服务器或密码。"
    )
    args_schema: Type[BaseModel] = EmailInput

    async def _arun(self, to_email: str, subject: str, content: str) -> str:
        """Use the tool asynchronously."""
        from app.core.context import get_current_agent_context
        from app.core.orm import AsyncSessionLocal
        from app.services.notification_service import NotificationService

        agent_ctx = get_current_agent_context()
        if not agent_ctx or not agent_ctx.user_id:
            return "Error: 无法确定当前用户，邮件未发送。"

        try:
            async with AsyncSessionLocal() as db:
                success, error = await NotificationService.send_email_to(
                    db,
                    agent_ctx.user_id,
                    to_email,
                    subject,
                    content,
                )
            if success:
                return f"Successfully sent email to {to_email}"
            return f"Failed to send email: {error}"
        except Exception as e:
            logger.error("Email Tool Error: %s", e, exc_info=True)
            return "Error sending email: 邮件服务暂时不可用"

    def _run(self, to_email: str, subject: str, content: str) -> str:
        raise NotImplementedError("Use _arun instead")

class WeChatWorkInput(BaseModel):
    content: str = Field(description="The main body of the message in Markdown format")

class send_wechat_work_message(BaseTool):
    name: str = "send_wechat_work_message"
    description: str = (
        "发送企业微信群机器人 Markdown 消息。Send a Markdown message to WeChat Work. "
        "本工具会自动读取当前用户在个人中心 -> 消息通知里的企微 Webhook 配置，"
        "无需用户在本轮对话中提供 webhook 或群聊目标。"
    )
    args_schema: Type[BaseModel] = WeChatWorkInput

    async def _arun(self, content: str) -> str:
        """Use the tool asynchronously."""
        from app.core.context import get_current_agent_context
        from app.core.orm import AsyncSessionLocal
        from app.services.notification_service import NotificationService

        agent_ctx = get_current_agent_context()
        if not agent_ctx or not agent_ctx.user_id:
            return "Error: WeChat Work Webhook URL not configured. Please go to Personal Center -> Message Notifications and set it."

        try:
            async with AsyncSessionLocal() as db:
                success, error = await NotificationService.send_wechat_work(
                    db,
                    agent_ctx.user_id,
                    "智能体通知",
                    content,
                )
            if success:
                return "Successfully sent WeChat Work message."
            return f"Failed to send WeChat Work message: {error}"
        except Exception as e:
            logger.error(f"WeChat Work Tool Error: {e}", exc_info=True)
            return f"Error executing WeChat Work tool: {str(e)}"

    def _run(self, content: str) -> str:
        raise NotImplementedError("Use _arun instead")


class PortalNotificationInput(BaseModel):
    title: str = Field(description="站内消息标题（门户铃铛与消息中心可见）")
    content: str = Field(description="站内消息正文（支持纯文本或 Markdown）")
    level: str = Field(
        default="info",
        description="消息级别：info / success / warning / error，默认 info",
    )


class send_portal_notification(BaseTool):
    name: str = "send_portal_notification"
    description: str = (
        "发送站内消息到当前用户的门户消息中心（右上角铃铛 / Inbox）。"
        "Send an in-app portal notification to the current user. "
        "无需配置 Webhook；消息会出现在 PortalNotification 站内信箱。"
        "适合任务完成提醒、巡检结论摘要、需要用户回门户查看的结果通知。"
    )
    args_schema: Type[BaseModel] = PortalNotificationInput

    async def _arun(self, title: str, content: str, level: str = "info") -> str:
        from app.core.context import get_current_agent_context
        from app.core.orm import AsyncSessionLocal
        from app.services.portal_notification_service import PortalNotificationService

        agent_ctx = get_current_agent_context()
        if not agent_ctx or not agent_ctx.user_id:
            return "Error: 无法确定当前用户，站内消息未发送。"

        try:
            user_id = int(agent_ctx.user_id)
        except (TypeError, ValueError):
            return "Error: 当前用户 ID 无效，站内消息未发送。"

        cleaned_title = str(title or "").strip()
        cleaned_content = str(content or "").strip()
        if not cleaned_title:
            return "Error: 标题不能为空。"
        if not cleaned_content:
            return "Error: 正文不能为空。"

        allowed_levels = {"info", "success", "warning", "error"}
        resolved_level = str(level or "info").strip().lower()
        if resolved_level not in allowed_levels:
            resolved_level = "info"

        try:
            async with AsyncSessionLocal() as db:
                row = await PortalNotificationService.create(
                    db,
                    user_id=user_id,
                    title=cleaned_title,
                    content=cleaned_content,
                    level=resolved_level,
                    category="agent",
                    resource_type="agent_message",
                    resource_id=str(getattr(agent_ctx, "conversation_id", "") or "")[:64] or None,
                    metadata={
                        "source": "send_portal_notification",
                        "agent_name": getattr(agent_ctx, "agent_name", None),
                        "conversation_id": getattr(agent_ctx, "conversation_id", None),
                    },
                )
                await db.commit()
            return (
                f"Successfully sent portal notification "
                f"(id={row.id}, level={resolved_level}): {cleaned_title}"
            )
        except Exception as e:
            logger.error("Portal notification tool error: %s", e, exc_info=True)
            return f"Error sending portal notification: {str(e)}"

    def _run(self, title: str, content: str, level: str = "info") -> str:
        raise NotImplementedError("Use _arun instead")
