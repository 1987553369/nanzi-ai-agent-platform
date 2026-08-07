import json
import logging
import time
import hmac
import hashlib
import base64
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_notification_config import UserNotificationConfig
from app.utils.outbound_url_policy import create_ssrf_safe_async_client
from app.utils.smtp_policy import send_smtp_message

logger = logging.getLogger(__name__)

class NotificationService:
    DEFAULT_CONFIGS = {
        "dingtalk": {
            "is_enabled": False,
            "webhook_url": "",
            "secret": ""
        },
        "wechat_work": {
            "is_enabled": False,
            "webhook_url": ""
        },
        "email": {
            "is_enabled": False,
            "smtp_host": "",
            "smtp_port": 465,
            "smtp_user": "",
            "smtp_password": "",
            "sender_name": "AI Agent"
        }
    }

    MASKED_KEYS = ["secret", "smtp_password"]

    @classmethod
    async def get_config_by_type_raw(
        cls, db: AsyncSession, user_id: int, channel_type: str
    ) -> Optional[UserNotificationConfig]:
        """Fetch raw notification config from DB by type"""
        stmt = select(UserNotificationConfig).where(
            UserNotificationConfig.user_id == user_id,
            UserNotificationConfig.channel_type == channel_type
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_user_configs(cls, db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Get all notification configs for a user with masking applied"""
        configs = {}
        for channel, default_val in cls.DEFAULT_CONFIGS.items():
            db_record = await cls.get_config_by_type_raw(db, user_id, channel)
            if db_record and db_record.config_json:
                try:
                    data = json.loads(db_record.config_json)
                except Exception as e:
                    logger.error(f"Failed to parse config_json for user {user_id}, channel {channel}: {e}")
                    data = {}
                
                # Merge with default structure to prevent missing keys
                merged = {**default_val, **data}
                # Apply mask to sensitive fields
                for k in cls.MASKED_KEYS:
                    if merged.get(k):
                        merged[k] = "******"
                configs[channel] = merged
            else:
                configs[channel] = {**default_val}
        return configs

    @classmethod
    async def save_user_config(
        cls, db: AsyncSession, user_id: int, channel_type: str, config_data: Dict[str, Any]
    ) -> UserNotificationConfig:
        """Save config for a specific channel, resolving masks back to real values"""
        if channel_type not in cls.DEFAULT_CONFIGS:
            raise ValueError(f"Unsupported channel type: {channel_type}")

        # Resolve masked values
        resolved_config = await cls.resolve_masked_config(db, user_id, channel_type, config_data)
        
        # Ensure type conversions (e.g., port to int for email)
        if channel_type == "email" and "smtp_port" in resolved_config:
            try:
                resolved_config["smtp_port"] = int(resolved_config["smtp_port"])
            except:
                resolved_config["smtp_port"] = 465

        db_record = await cls.get_config_by_type_raw(db, user_id, channel_type)
        if db_record:
            db_record.config_json = json.dumps(resolved_config, ensure_ascii=False)
        else:
            db_record = UserNotificationConfig(
                user_id=user_id,
                channel_type=channel_type,
                config_json=json.dumps(resolved_config, ensure_ascii=False)
            )
            db.add(db_record)
            
        await db.commit()
        await db.refresh(db_record)
        return db_record

    @classmethod
    async def resolve_masked_config(
        cls, db: AsyncSession, user_id: int, channel_type: str, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve masked '******' values back to their actual stored values"""
        db_record = await cls.get_config_by_type_raw(db, user_id, channel_type)
        existing_data = {}
        if db_record and db_record.config_json:
            try:
                existing_data = json.loads(db_record.config_json)
            except Exception as e:
                logger.warning(f"Failed to parse existing config json: {e}")
                
        resolved = {**config_data}
        for k in cls.MASKED_KEYS:
            if resolved.get(k) == "******":
                resolved[k] = existing_data.get(k, "")
        return resolved

    @classmethod
    async def test_connection(cls, channel_type: str, config_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Test notification channel connectivity using actual config data"""
        if channel_type == "dingtalk":
            return await cls._test_dingtalk(config_data)
        elif channel_type == "wechat_work":
            return await cls._test_wechat_work(config_data)
        elif channel_type == "email":
            return await cls._test_email(config_data)
        return False, f"Unsupported channel type: {channel_type}"

    @classmethod
    async def _test_dingtalk(cls, config: Dict[str, Any]) -> Tuple[bool, str]:
        webhook_url = config.get("webhook_url")
        secret = config.get("secret")
        if not webhook_url:
            return False, "Webhook 地址不能为空"
        
        try:
            target_url = webhook_url
            if secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f'{timestamp}\n{secret}'
                hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                separator = "&" if "?" in webhook_url else "?"
                target_url = f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "消息通知连通性测试",
                    "text": "### 消息通知连通性测试\n\n您的AI 智能体平台个人中心钉钉通知渠道已配置成功，测试消息发送正常。"
                }
            }

            async with create_ssrf_safe_async_client(
                allowed_url=target_url,
                timeout=10.0,
            ) as client:
                response = await client.post(target_url, json=payload)
                response.raise_for_status()
                resp_data = response.json()
                if resp_data.get("errcode") == 0:
                    return True, ""
                else:
                    return False, f"{resp_data.get('errmsg')} (Code: {resp_data.get('errcode')})"
        except Exception as e:
            return False, str(e)

    @classmethod
    async def _test_wechat_work(cls, config: Dict[str, Any]) -> Tuple[bool, str]:
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            return False, "Webhook 地址不能为空"
            
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": "### 消息通知连通性测试\n\n您的AI 智能体平台个人中心企业微信通知渠道已配置成功，测试消息发送正常。"
                }
            }
            async with create_ssrf_safe_async_client(
                allowed_url=webhook_url,
                timeout=10.0,
            ) as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                resp_data = response.json()
                if resp_data.get("errcode") == 0:
                    return True, ""
                else:
                    return False, f"{resp_data.get('errmsg')} (Code: {resp_data.get('errcode')})"
        except Exception as e:
            return False, str(e)

    @classmethod
    async def _test_email(cls, config: Dict[str, Any]) -> Tuple[bool, str]:
        smtp_host = config.get("smtp_host")
        smtp_user = config.get("smtp_user")
        smtp_password = config.get("smtp_password")
        if not smtp_host or not smtp_user or not smtp_password:
            return False, "SMTP 服务地址、账号和授权码不能为空"

        try:
            return await cls._send_email_msg_real(
                config,
                smtp_user,
                "AI 智能体平台 - 邮件通知连通性测试",
                "这是一封来自AI 智能体平台的测试邮件，表明您的邮件通知通道配置已测试成功。",
            )
        except Exception as e:
            logger.error("SMTP connectivity test failed: %s", e, exc_info=True)
            return False, "SMTP 连接或发送失败，请检查配置和网络策略"

    # Core message sending APIs for user configured channels
    @classmethod
    async def send_dingtalk(cls, db: AsyncSession, user_id: int, title: str, content: str) -> Tuple[bool, str]:
        """Send message using user's configured DingTalk channel"""
        db_record = await cls.get_config_by_type_raw(db, user_id, "dingtalk")
        if not db_record or not db_record.config_json:
            return False, "用户未配置钉钉通知"
            
        data = json.loads(db_record.config_json)
        if not data.get("is_enabled"):
            return False, "用户未启用钉钉通知"
            
        return await cls._send_dingtalk_msg_real(data, title, content)

    @classmethod
    async def _send_dingtalk_msg_real(cls, config: Dict[str, Any], title: str, content: str) -> Tuple[bool, str]:
        webhook_url = config.get("webhook_url")
        secret = config.get("secret")
        try:
            target_url = webhook_url
            if secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f'{timestamp}\n{secret}'
                hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                separator = "&" if "?" in webhook_url else "?"
                target_url = f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"### {title}\n\n{content}"
                }
            }

            async with create_ssrf_safe_async_client(
                allowed_url=target_url,
                timeout=10.0,
            ) as client:
                response = await client.post(target_url, json=payload)
                response.raise_for_status()
                resp_data = response.json()
                if resp_data.get("errcode") == 0:
                    return True, ""
                else:
                    return False, f"{resp_data.get('errmsg')} (Code: {resp_data.get('errcode')})"
        except Exception as e:
            return False, str(e)

    @classmethod
    async def send_wechat_work(cls, db: AsyncSession, user_id: int, title: str, content: str) -> Tuple[bool, str]:
        record = await cls.get_config_by_type_raw(db, user_id, "wechat_work")
        if not record or not record.config_json:
            return False, "用户未配置企业微信通知"
        config = json.loads(record.config_json)
        if not config.get("is_enabled") or not config.get("webhook_url"):
            return False, "用户未启用企业微信通知"
        try:
            payload = {"msgtype": "markdown", "markdown": {"content": f"### {title}\n\n{content}"}}
            webhook_url = config["webhook_url"]
            async with create_ssrf_safe_async_client(
                allowed_url=webhook_url,
                timeout=10.0,
            ) as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                data = response.json()
            return (True, "") if data.get("errcode") == 0 else (False, str(data.get("errmsg") or data))
        except Exception as exc:
            return False, str(exc)

    @classmethod
    async def send_email(cls, db: AsyncSession, user_id: int, title: str, content: str) -> Tuple[bool, str]:
        return await cls.send_email_to(db, user_id, None, title, content)

    @classmethod
    async def send_email_to(
        cls,
        db: AsyncSession,
        user_id: int,
        to_email: Optional[str],
        title: str,
        content: str,
    ) -> Tuple[bool, str]:
        record = await cls.get_config_by_type_raw(db, user_id, "email")
        if not record or not record.config_json:
            return False, "用户未配置邮件通知"
        config = json.loads(record.config_json)
        if not config.get("is_enabled"):
            return False, "用户未启用邮件通知"
        recipient = str(to_email or config.get("smtp_user") or "").strip()
        try:
            return await cls._send_email_msg_real(config, recipient, title, content)
        except Exception as exc:
            logger.error("SMTP send failed: %s", exc, exc_info=True)
            return False, "邮件发送失败，请检查 SMTP 配置和网络策略"

    @classmethod
    async def _send_email_msg_real(
        cls,
        config: Dict[str, Any],
        to_email: str,
        title: str,
        content: str,
    ) -> Tuple[bool, str]:
        host = str(config.get("smtp_host") or "").strip()
        username = str(config.get("smtp_user") or "").strip()
        password = str(config.get("smtp_password") or "")
        recipient = str(to_email or "").strip()
        subject = str(title or "")
        body = str(content or "")
        sender_name = str(config.get("sender_name") or "AI Agent")
        if not host or not username or not password or not recipient:
            return False, "SMTP 配置或收件人不完整"
        if any(
            "\r" in value or "\n" in value
            for value in (username, recipient, subject, sender_name)
        ):
            return False, "邮件地址或主题格式无效"
        try:
            port = int(config.get("smtp_port") or 465)
        except (TypeError, ValueError):
            return False, "SMTP 端口格式错误"

        message = MIMEMultipart()
        message["From"] = formataddr((sender_name, username))
        message["To"] = recipient
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))
        await send_smtp_message(
            hostname=host,
            port=port,
            username=username,
            password=password,
            recipient=recipient,
            message=message.as_string(),
            timeout=10.0,
        )
        return True, ""
