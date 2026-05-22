"""Tests for main.py 应用启动 / CORS 中间件装配 / 健康检查"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


@pytest.fixture
def app_client():
    """构造一个使用固定白名单的精简 app,绕过 lifespan/bootstrap 测试 CORS"""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://allowed.example.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return TestClient(app)


def test_health_endpoint_returns_ok(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cors_blocks_unlisted_origin(app_client):
    """未在白名单的 origin 不应被授予 ACAO 头"""
    r = app_client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") != "http://evil.com"


def test_cors_allows_listed_origin(app_client):
    r = app_client.options(
        "/api/health",
        headers={
            "Origin": "http://allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://allowed.example.com"


def test_dockerfile_has_no_reload_flag():
    """Dockerfile 生产 CMD 不应包含 --reload"""
    dockerfile = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Dockerfile",
    )
    with open(dockerfile, "r", encoding="utf-8") as f:
        content = f.read()
    assert "--reload" not in content, "生产 Dockerfile 不能含 --reload(开发模式)"


def test_dockerfile_uses_gunicorn():
    """生产应使用 gunicorn 多 worker"""
    dockerfile = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Dockerfile",
    )
    with open(dockerfile, "r", encoding="utf-8") as f:
        content = f.read()
    assert "gunicorn" in content, "Dockerfile CMD 应使用 gunicorn"
    assert "UvicornWorker" in content, "应使用 uvicorn.workers.UvicornWorker"


def test_main_app_includes_cors_middleware():
    """实际 main.py 应用应正确装配 CORS 中间件"""
    import main as main_module
    middlewares = [
        m for m in main_module.app.user_middleware
        if "CORSMiddleware" in str(m.cls)
    ]
    assert len(middlewares) >= 1, "main.py 应注册 CORSMiddleware"


def test_settings_cors_origins_is_list_not_wildcard():
    """settings.CORS_ORIGINS 应为 list,默认不含 '*'"""
    from app.core.config import settings
    assert isinstance(settings.CORS_ORIGINS, list)
    assert "*" not in settings.CORS_ORIGINS, "默认 CORS 不应含 '*'"
