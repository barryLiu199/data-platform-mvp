"""通知发送工具 — 支持邮件和飞书 Webhook"""
import logging
import smtplib
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


async def notify(rule, event: dict) -> bool:
    """根据规则的通知类型分发通知

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


async def send_dingtalk_webhook(webhook_url: str, title: str, content: str) -> bool:
    """发送钉钉机器人消息"""
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
        return await send_dingtalk_webhook(config.get("webhook_url", ""), title, content)
    elif channel_type == "wecom":
        return await send_wecom_webhook(config.get("webhook_url", ""), title, content)
    elif channel_type == "email":
        return send_email(config.get("email", "test@test.com"), title, content, config)
    else:
        logger.warning(f"未知渠道类型: {channel_type}")
        return False
