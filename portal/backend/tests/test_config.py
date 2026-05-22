"""Tests for app/core/config.py — CORS / Cookie / 关键安全配置"""
import importlib
import os

import pytest


def _reload_settings():
    """重新加载 settings,使新的环境变量生效"""
    import app.core.config as cfg
    importlib.reload(cfg)
    return cfg.settings


def test_cors_origins_default_is_wildcard_only_in_dev(monkeypatch):
    """无 env 时默认本地开发地址,不应是裸 *"""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = _reload_settings()
    # 关键断言:生产部署必须能从 env 注入,默认值不能再是 ["*"]
    assert settings.CORS_ORIGINS != ["*"], "默认 CORS 不能是 ['*'],会导致跨域风险"


def test_cors_origins_parses_comma_separated_env(monkeypatch):
    """环境变量 CORS_ORIGINS 用逗号分隔"""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://39.98.46.227,https://example.com",
    )
    settings = _reload_settings()
    assert "http://39.98.46.227" in settings.CORS_ORIGINS
    assert "https://example.com" in settings.CORS_ORIGINS
    assert len(settings.CORS_ORIGINS) == 2


def test_cors_origins_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " http://a.com , http://b.com ")
    settings = _reload_settings()
    assert settings.CORS_ORIGINS == ["http://a.com", "http://b.com"]


def test_cookie_secure_defaults_false_for_dev(monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    settings = _reload_settings()
    assert settings.COOKIE_SECURE is False


def test_cookie_secure_can_be_set_true(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    settings = _reload_settings()
    assert settings.COOKIE_SECURE is True


def test_redis_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://:pwd@redis:6379/0")
    settings = _reload_settings()
    assert settings.REDIS_URL == "redis://:pwd@redis:6379/0"


def test_ds_admin_password_can_be_overridden(monkeypatch):
    monkeypatch.setenv("DS_ADMIN_PASSWORD", "ds-secret-from-env")
    settings = _reload_settings()
    assert settings.DS_ADMIN_PASSWORD == "ds-secret-from-env"
