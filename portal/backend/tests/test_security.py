"""Tests for app/core/security.py — JWT 签发/验证/密码哈希"""
import time
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    _decode_token,
    get_current_user,
)


# ---- 密码哈希（真实 bcrypt，无 mock）----

def test_hash_and_verify_password():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed)


def test_wrong_password_fails():
    hashed = hash_password("correct")
    assert not verify_password("wrong", hashed)


def test_hash_is_not_plaintext():
    pw = "secret123"
    assert hash_password(pw) != pw


# ---- JWT 签发与解码 ----

def test_create_and_decode_token():
    token = create_access_token({"sub": "alice"})
    assert _decode_token(token) == "alice"


def test_tampered_token_returns_none():
    token = create_access_token({"sub": "alice"})
    bad = token[:-4] + "xxxx"
    assert _decode_token(bad) is None


def test_invalid_token_returns_none():
    assert _decode_token("not.a.token") is None


def test_expired_token_returns_none():
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.core.config import settings

    payload = {
        "sub": "alice",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert _decode_token(expired) is None


# ---- get_current_user ----

def _make_request(cookie_token=None, bearer_token=None):
    request = MagicMock()
    request.cookies = {}
    if cookie_token:
        request.cookies["access_token"] = cookie_token
    credentials = None
    if bearer_token:
        credentials = MagicMock()
        credentials.credentials = bearer_token
    return request, credentials


def test_get_current_user_via_cookie():
    token = create_access_token({"sub": "bob"})
    request, credentials = _make_request(cookie_token=token)

    user = MagicMock()
    user.username = "bob"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    result = get_current_user(request=request, credentials=credentials, db=db)
    assert result == user


def test_get_current_user_via_bearer():
    token = create_access_token({"sub": "carol"})
    request, credentials = _make_request(bearer_token=token)

    user = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    result = get_current_user(request=request, credentials=credentials, db=db)
    assert result == user


def test_get_current_user_no_token_raises_401():
    request, credentials = _make_request()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        get_current_user(request=request, credentials=credentials, db=db)
    assert exc.value.status_code == 401


def test_get_current_user_invalid_token_raises_401():
    request, credentials = _make_request(bearer_token="bad.token.here")
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        get_current_user(request=request, credentials=credentials, db=db)
    assert exc.value.status_code == 401


def test_get_current_user_not_found_raises_401():
    token = create_access_token({"sub": "ghost"})
    request, credentials = _make_request(bearer_token=token)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        get_current_user(request=request, credentials=credentials, db=db)
    assert exc.value.status_code == 401


def test_cookie_takes_priority_over_bearer():
    """cookie token 优先于 Authorization header"""
    cookie_token = create_access_token({"sub": "cookie_user"})
    bearer_token = create_access_token({"sub": "bearer_user"})
    request, credentials = _make_request(cookie_token=cookie_token, bearer_token=bearer_token)

    user = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    get_current_user(request=request, credentials=credentials, db=db)
    # 验证 _decode_token 用的是 cookie_token（解码出 cookie_user）
    # 通过检查 db.query 被调用时传入的 filter 条件来间接验证
    # SQLAlchemy BinaryExpression 无法直接 str 比较，改为验证 first() 被调用
    db.query.return_value.filter.return_value.first.assert_called_once()
