from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Cookie
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import defaultdict
from threading import Lock

from app.core.database import get_db
from app.core.security import verify_password, create_access_token, hash_password, get_current_user, _COOKIE_NAME
from app.core.config import settings
from app.models.user import SysUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["认证"])

# 登录暴力破解防护：按 IP 计数，优先用 Redis（多实例共享），不可用时降级内存
_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()
_redis_client = None
_redis_init_lock = Lock()


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis as redis_lib
            r = redis_lib.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1,
            )
            r.ping()
            _redis_client = r
            return _redis_client
        except Exception as e:
            logger.warning("Redis unavailable for rate limiting: %s", e)
            return None


def _check_login_rate(ip: str) -> None:
    r = _get_redis()
    now = time.time()
    if r:
        key = f"login_attempts:{ip}"
        raw = r.get(key)
        attempts = json.loads(raw) if raw else []
        attempts = [t for t in attempts if now - t < settings.LOGIN_LOCKOUT_SECONDS]
        if len(attempts) >= settings.LOGIN_MAX_ATTEMPTS:
            retry_after = int(settings.LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录尝试过于频繁，请 {retry_after} 秒后再试",
            )
    else:
        with _login_lock:
            attempts = [t for t in _login_attempts[ip] if now - t < settings.LOGIN_LOCKOUT_SECONDS]
            _login_attempts[ip] = attempts
            if len(attempts) >= settings.LOGIN_MAX_ATTEMPTS:
                retry_after = int(settings.LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"登录尝试过于频繁，请 {retry_after} 秒后再试",
                )


def _record_failed_login(ip: str) -> None:
    r = _get_redis()
    now = time.time()
    if r:
        key = f"login_attempts:{ip}"
        raw = r.get(key)
        attempts = json.loads(raw) if raw else []
        attempts.append(now)
        r.setex(key, settings.LOGIN_LOCKOUT_SECONDS, json.dumps(attempts))
    else:
        with _login_lock:
            _login_attempts[ip].append(now)


def _clear_login_attempts(ip: str) -> None:
    r = _get_redis()
    if r:
        r.delete(f"login_attempts:{ip}")
    else:
        with _login_lock:
            _login_attempts.pop(ip, None)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate(client_ip)
    user = db.query(SysUser).filter(SysUser.username == req.username).first()
    if not user or not verify_password(req.password, user.password):
        _record_failed_login(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    _clear_login_attempts(client_ip)

    token = create_access_token(data={"sub": user.username})
    # 同时设置 httponly cookie，前端 axios withCredentials 可自动携带
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return LoginResponse(
        access_token=token,
        user={
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "role": user.role,
            "email": user.email,
        },
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(_COOKIE_NAME, httponly=True, samesite="lax")
    return {"ok": True}


@router.get("/me")
def get_me(current_user: SysUser = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "role": current_user.role,
        "email": current_user.email,
        "phone": current_user.phone,
    }


@router.get("/me/permissions")
def get_my_permissions(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回当前用户的权限码列表"""
    from app.core.permissions import _is_admin
    if _is_admin(db, current_user):
        from app.models.role import SysPermission
        perms = db.query(SysPermission).all()
        return {"permissions": [p.code for p in perms]}

    from app.models.role import SysUserRole, SysRolePermission, SysPermission
    perms = (
        db.query(SysPermission)
        .join(SysRolePermission, SysRolePermission.permission_id == SysPermission.id)
        .join(SysUserRole, SysUserRole.role_id == SysRolePermission.role_id)
        .filter(SysUserRole.user_id == current_user.id)
        .all()
    )
    return {"permissions": list({p.code for p in perms})}


@router.put("/password")
def change_password(
    req: ChangePasswordRequest,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.old_password, current_user.password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    current_user.password = hash_password(req.new_password)
    db.commit()
    return {"message": "密码修改成功"}


# ─── SSO OAuth2 ──────────────────────────────────────────────────────────────


def _sign_state(state: str, provider: str) -> str:
    """生成签名 state cookie 值"""
    from app.core.config import settings
    payload = json.dumps({"state": state, "provider": provider})
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(cookie_value: str, state: str, provider: str) -> bool:
    """验证 state cookie 签名和内容"""
    from app.core.config import settings
    try:
        payload, sig = cookie_value.rsplit(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        stored = json.loads(payload)
        return stored["state"] == state and stored["provider"] == provider
    except Exception:
        return False


@router.get("/oauth/{provider}")
async def oauth_redirect(provider: str, db: Session = Depends(get_db)):
    """重定向到第三方授权页，设置签名 state cookie 防 CSRF"""
    from app.models.oauth_config import SysOAuthConfig
    from app.core.oauth import get_authorize_url
    cfg = db.query(SysOAuthConfig).filter(
        SysOAuthConfig.provider == provider,
        SysOAuthConfig.enabled == True,
    ).first()
    if not cfg:
        raise HTTPException(400, f"SSO 提供商 {provider} 未启用")
    state = secrets.token_urlsafe(16)
    url = get_authorize_url(provider, cfg.app_id, cfg.redirect_uri, state)
    response = RedirectResponse(url)
    response.set_cookie(
        key="oauth_state",
        value=_sign_state(state, provider),
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=600,
    )
    return response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str = "",
    oauth_state: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """OAuth2 授权码回调，验证 state 防 CSRF，签发 JWT"""
    # CSRF 校验
    if not oauth_state or not _verify_state(oauth_state, state, provider):
        raise HTTPException(400, "OAuth state 验证失败，请重新登录")

    from app.models.oauth_config import SysOAuthConfig
    from app.core.oauth import exchange_code_for_user
    cfg = db.query(SysOAuthConfig).filter(
        SysOAuthConfig.provider == provider,
        SysOAuthConfig.enabled == True,
    ).first()
    if not cfg:
        raise HTTPException(400, f"SSO 提供商 {provider} 未启用")

    try:
        user_info = await exchange_code_for_user(
            provider, code, cfg.app_id, cfg.app_secret, cfg.redirect_uri
        )
    except Exception as e:
        logger.error(f"OAuth exchange failed for provider={provider}: {e}", exc_info=True)
        raise HTTPException(400, "OAuth 授权失败，请重试")

    openid = user_info.get("openid", "")
    if not openid:
        raise HTTPException(400, "无法获取用户 openid")

    # 查找已绑定的用户
    user = db.query(SysUser).filter(
        SysUser.oauth_provider == provider,
        SysUser.oauth_openid == openid,
    ).first()

    if not user:
        # 用 sha256 hash 生成稳定且唯一的用户名，避免截断碰撞
        short_hash = hashlib.sha256(openid.encode()).hexdigest()[:12]
        username = f"{provider}_{short_hash}"
        existing = db.query(SysUser).filter(SysUser.username == username).first()
        if existing:
            # 已有同名用户但无 OAuth 绑定 → 拒绝，避免账号劫持
            if existing.oauth_provider is None:
                raise HTTPException(409, "用户名冲突，请联系管理员手动绑定账号")
            # 同一 OAuth 身份（正常情况，上面 filter 应已命中，此处兜底）
            user = existing
        else:
            user = SysUser(
                username=username,
                password=hash_password(secrets.token_hex(16)),
                real_name=user_info.get("name", username),
                email=user_info.get("email"),
                avatar=user_info.get("avatar"),
                oauth_provider=provider,
                oauth_openid=openid,
                status=1,
                role="user",
            )
            db.add(user)
            try:
                db.flush()
            except IntegrityError:
                # 并发创建竞态：另一个请求已插入，回滚后重新查询
                db.rollback()
                user = db.query(SysUser).filter(
                    SysUser.oauth_provider == provider,
                    SysUser.oauth_openid == openid,
                ).first()
                if not user:
                    raise HTTPException(500, "用户创建失败，请重试")
            else:
                # 默认分配 viewer 角色
                from app.models.role import SysRole, SysUserRole
                viewer = db.query(SysRole).filter(SysRole.code == "viewer").first()
                if viewer:
                    db.add(SysUserRole(user_id=user.id, role_id=viewer.id))

        db.commit()
        db.refresh(user)

    if user.status != 1:
        raise HTTPException(403, "账号已禁用")

    token = create_access_token(data={"sub": user.username})
    # token 放在 hash fragment，不会出现在服务器日志和 Referer 头中
    # 同时设置 httponly cookie，后续请求可自动携带
    response = RedirectResponse(f"/oauth-callback#token={token}")
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.delete_cookie("oauth_state", httponly=True, samesite="lax")
    return response
