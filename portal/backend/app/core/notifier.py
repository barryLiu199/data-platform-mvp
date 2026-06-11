"""通知发送工具 — 支持邮件 / 飞书 / 钉钉 / 企微 Webhook，支持多渠道分发"""
import base64
import hashlib
import hmac
import logging
import smtplib
import time
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

logger = logging.getLogger(__name__)


async def send_feishu_webhook(webhook_url: str, title: str, content: str) -> bool:
    """发送飞书机器人消息（富文本卡片）"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 or data.get("StatusCode") == 0:
                    return True
                logger.warning(f"飞书 Webhook 返回错误: {data}")
                return False
            logger.warning(f"飞书 Webhook HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"飞书 Webhook 发送失败: {e}")
        return False


def send_email(to: str, subject: str, body: str, smtp_config: dict = None) -> bool:
    """发送邮件通知"""
    # 默认 SMTP 配置（可通过环境变量或参数覆盖）
    import os
    config = smtp_config or {
        "host": os.getenv("SMTP_HOST", "smtp.163.com"),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "use_ssl": os.getenv("SMTP_SSL", "true").lower() == "true",
    }
    if not config["user"]:
        logger.warning("SMTP 未配置，跳过邮件发送")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = config["user"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html", "utf-8"))
        if config["use_ssl"]:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10)
        else:
            server = smtplib.SMTP(config["host"], config["port"], timeout=10)
            server.starttls()
        server.login(config["user"], config["password"])
        server.sendmail(config["user"], [to], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


async def _send_via_channel(channel, title: str, content: str) -> bool:
    """通过 SysNotifyChannel 渠道对象发送通知"""
    ctype = channel.channel_type
    config = channel.config or {}

    if ctype == "feishu_webhook":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"渠道 {channel.name} 飞书 Webhook URL 为空")
            return False
        return await send_feishu_webhook(url, title, content)

    elif ctype == "dingtalk":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"渠道 {channel.name} 钉钉 Webhook URL 为空")
            return False
        return await send_dingtalk_webhook(url, title, content, secret=config.get("secret", ""))

    elif ctype == "wecom":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"渠道 {channel.name} 企微 Webhook URL 为空")
            return False
        return await send_wecom_webhook(url, title, content)

    elif ctype == "email":
        email = config.get("email", "")
        if not email:
            logger.warning(f"渠道 {channel.name} 邮箱地址为空")
            return False
        html_body = content.replace("\n", "<br>")
        return send_email(email, title, html_body, config if config.get("host") else None)

    logger.warning(f"渠道 {channel.name} 类型不支持: {ctype}")
    return False


async def notify(rule, event: dict) -> bool:
    """根据规则的通知配置分发通知

    优先走多渠道（rule.notify_channel_ids → SysNotifyChannel），
    未配置渠道时降级为旧的单渠道 notify_type/notify_config。

    Args:
        rule: AlertRule 对象
        event: {"workflow_name": str, "status": str, "time": str, "duration": int}
    """
    wf_name = event.get("workflow_name", "未知工作流")
    status = event.get("status", "FAILURE")
    run_time = event.get("time", "")
    duration = event.get("duration")

    title = f"⚠ 告警: {wf_name} {status}"
    content = (
        f"**工作流**: {wf_name}\n"
        f"**状态**: {status}\n"
        f"**时间**: {run_time}\n"
    )
    if duration is not None:
        content += f"**耗时**: {duration}s\n"
    content += f"**规则**: {rule.name}"

    # 多渠道分发（任一渠道成功即视为成功）
    channel_ids = getattr(rule, "notify_channel_ids", None)
    if channel_ids:
        from app.core.database import SessionLocal
        from app.models.sys_notify_channel import SysNotifyChannel

        db = SessionLocal()
        try:
            channels = (
                db.query(SysNotifyChannel)
                .filter(SysNotifyChannel.id.in_(channel_ids), SysNotifyChannel.enabled == True)
                .all()
            )
        finally:
            db.close()
        if channels:
            results = [await _send_via_channel(ch, title, content) for ch in channels]
            return any(results)
        logger.warning(f"规则 {rule.name} 配置的渠道均不可用: {channel_ids}")
        return False

    config = rule.notify_config or {}

    if rule.notify_type == "feishu_webhook":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"规则 {rule.name} 飞书 Webhook URL 为空")
            return False
        return await send_feishu_webhook(url, title, content)

    elif rule.notify_type == "email":
        email = config.get("email", "")
        if not email:
            logger.warning(f"规则 {rule.name} 邮箱地址为空")
            return False
        html_body = content.replace("\n", "<br>").replace("**", "<b>").replace("**", "</b>")
        return send_email(email, title, html_body)

    elif rule.notify_type == "dingtalk":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"规则 {rule.name} 钉钉 Webhook URL 为空")
            return False
        return await send_dingtalk_webhook(url, title, content)

    elif rule.notify_type == "wecom":
        url = config.get("webhook_url", "")
        if not url:
            logger.warning(f"规则 {rule.name} 企微 Webhook URL 为空")
            return False
        return await send_wecom_webhook(url, title, content)

    else:
        logger.warning(f"不支持的通知类型: {rule.notify_type}")
        return False


def _dingtalk_sign_url(webhook_url: str, secret: str) -> str:
    """钉钉机器人加签：在 URL 上追加 timestamp + sign 参数"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}timestamp={timestamp}&sign={sign}"


async def send_dingtalk_webhook(webhook_url: str, title: str, content: str, secret: str = "") -> bool:
    """发送钉钉机器人消息（secret 非空时走加签安全设置）"""
    if secret:
        webhook_url = _dingtalk_sign_url(webhook_url, secret)
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": f"### {title}\n{content}"},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errcode") == 0:
                    return True
                logger.warning(f"钉钉 Webhook 返回错误: {data}")
                return False
            return False
    except Exception as e:
        logger.error(f"钉钉 Webhook 发送失败: {e}")
        return False


async def send_wecom_webhook(webhook_url: str, title: str, content: str) -> bool:
    """发送企业微信机器人消息"""
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": f"### {title}\n{content}"},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errcode") == 0:
                    return True
                logger.warning(f"企微 Webhook 返回错误: {data}")
                return False
            return False
    except Exception as e:
        logger.error(f"企微 Webhook 发送失败: {e}")
        return False


async def test_channel(channel_type: str, config: dict) -> bool:
    """测试通知渠道连通性"""
    title = "测试通知"
    content = "这是一条通知渠道测试消息，收到说明配置正确。"
    if channel_type == "feishu_webhook":
        return await send_feishu_webhook(config.get("webhook_url", ""), title, content)
    elif channel_type == "dingtalk":
        return await send_dingtalk_webhook(
            config.get("webhook_url", ""), title, content, secret=config.get("secret", "")
        )
    elif channel_type == "wecom":
        return await send_wecom_webhook(config.get("webhook_url", ""), title, content)
    elif channel_type == "email":
        return send_email(config.get("email", "test@test.com"), title, content, config)
    else:
        logger.warning(f"未知渠道类型: {channel_type}")
        return False
