"""Tests for app/core/notifier.py — 通知发送逻辑"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


# ---- send_feishu_webhook ----

@pytest.mark.asyncio
async def test_feishu_webhook_success():
    from app.core.notifier import send_feishu_webhook

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 0}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await send_feishu_webhook("https://example.com/hook", "title", "content")
    assert result is True


@pytest.mark.asyncio
async def test_feishu_webhook_api_error():
    from app.core.notifier import send_feishu_webhook

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 19001, "msg": "invalid"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await send_feishu_webhook("https://example.com/hook", "title", "content")
    assert result is False


@pytest.mark.asyncio
async def test_feishu_webhook_network_error():
    from app.core.notifier import send_feishu_webhook

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client_cls.return_value = mock_client

        result = await send_feishu_webhook("https://example.com/hook", "title", "content")
    assert result is False


# ---- send_dingtalk_webhook ----

@pytest.mark.asyncio
async def test_dingtalk_webhook_success():
    from app.core.notifier import send_dingtalk_webhook

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"errcode": 0}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await send_dingtalk_webhook("https://oapi.dingtalk.com/robot/send?access_token=xxx", "title", "content")
    assert result is True


@pytest.mark.asyncio
async def test_dingtalk_webhook_with_secret_adds_sign():
    from app.core.notifier import send_dingtalk_webhook

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"errcode": 0}

    posted_urls = []

    async def capture_post(url, **kwargs):
        posted_urls.append(url)
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = capture_post
        mock_client_cls.return_value = mock_client

        await send_dingtalk_webhook("https://oapi.dingtalk.com/robot/send?access_token=xxx",
                                    "title", "content", secret="mysecret")

    assert len(posted_urls) == 1
    assert "timestamp=" in posted_urls[0]
    assert "sign=" in posted_urls[0]


# ---- send_email ----

def test_send_email_no_user_returns_false():
    from app.core.notifier import send_email
    result = send_email("to@example.com", "subject", "body", smtp_config={"user": "", "host": "smtp.test.com", "port": 465})
    assert result is False


def test_send_email_smtp_failure_returns_false():
    from app.core.notifier import send_email

    mock_server = MagicMock()
    mock_server.login.side_effect = Exception("auth failed")

    with patch("smtplib.SMTP_SSL", return_value=mock_server):
        result = send_email("to@example.com", "subject", "body", smtp_config={
            "user": "sender@test.com", "password": "pw",
            "host": "smtp.test.com", "port": 465, "use_ssl": True,
        })
    assert result is False


# ---- _send_via_channel ----

@pytest.mark.asyncio
async def test_send_via_channel_feishu():
    from app.core.notifier import _send_via_channel

    channel = MagicMock()
    channel.channel_type = "feishu_webhook"
    channel.config = {"webhook_url": "https://example.com/hook"}
    channel.name = "test"

    with patch("app.core.notifier.send_feishu_webhook", new_callable=AsyncMock, return_value=True) as mock_send:
        result = await _send_via_channel(channel, "title", "content")
    assert result is True
    mock_send.assert_called_once_with("https://example.com/hook", "title", "content")


@pytest.mark.asyncio
async def test_send_via_channel_missing_url_returns_false():
    from app.core.notifier import _send_via_channel

    channel = MagicMock()
    channel.channel_type = "feishu_webhook"
    channel.config = {}  # no webhook_url
    channel.name = "empty"

    result = await _send_via_channel(channel, "title", "content")
    assert result is False


@pytest.mark.asyncio
async def test_send_via_channel_unknown_type_returns_false():
    from app.core.notifier import _send_via_channel

    channel = MagicMock()
    channel.channel_type = "sms"
    channel.config = {}
    channel.name = "sms_channel"

    result = await _send_via_channel(channel, "title", "content")
    assert result is False


# ---- notify (旧逻辑降级) ----

@pytest.mark.asyncio
async def test_notify_legacy_feishu():
    from app.core.notifier import notify

    rule = MagicMock()
    rule.name = "test_rule"
    rule.notify_type = "feishu_webhook"
    rule.notify_config = {"webhook_url": "https://example.com/hook"}
    rule.notify_channel_ids = None

    with patch("app.core.notifier.send_feishu_webhook", new_callable=AsyncMock, return_value=True):
        result = await notify(rule, {"workflow_name": "wf1", "status": "FAILURE", "time": "2026-01-01"})
    assert result is True


@pytest.mark.asyncio
async def test_notify_no_config_returns_false():
    from app.core.notifier import notify

    rule = MagicMock()
    rule.name = "empty_rule"
    rule.notify_type = "unknown"
    rule.notify_config = {}
    rule.notify_channel_ids = None

    result = await notify(rule, {"workflow_name": "wf", "status": "FAILURE", "time": ""})
    assert result is False
