import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, SessionLocal
from app.core.config import settings
from app.core.security import hash_password
from app.core.migrations import run_all_migrations
from app.api import auth, datasources, sync_tasks, dashboard, ds_proxy, notifications, component, workflow, system, metadata, project
from app.models.component_folder import ComponentFolder  # noqa: F401
from app.models.role import SysRole, SysPermission, SysRolePermission, SysUserRole  # noqa: F401
from app.models.resource_access import SysResourceAccess  # noqa: F401
from app.models.oauth_config import SysOAuthConfig  # noqa: F401
from app.models.sys_config import SysConfig  # noqa: F401
from app.models.sys_notify_channel import SysNotifyChannel  # noqa: F401

# 创建表
Base.metadata.create_all(bind=engine)
run_all_migrations()


# ─── 种子数据：4 个内置角色 + 权限列表 ──────────────────────────────────────

_BUILTIN_PERMISSIONS = [
    ("user:manage",       "用户管理",       "user",       "manage"),
    ("role:manage",       "角色管理",       "role",       "manage"),
    ("system:config",     "系统配置",       "system",     "config"),
    ("datasource:read",   "数据源查看",     "datasource", "read"),
    ("datasource:write",  "数据源编辑",     "datasource", "write"),
    ("component:read",    "组件查看",       "component",  "read"),
    ("component:create",  "组件创建",       "component",  "create"),
    ("component:write",   "组件编辑",       "component",  "write"),
    ("component:publish", "组件发布/下线",  "component",  "publish"),
    ("workflow:read",     "工作流查看",     "workflow",   "read"),
    ("workflow:create",   "工作流创建",     "workflow",   "create"),
    ("workflow:write",    "工作流编辑",     "workflow",   "write"),
    ("workflow:publish",  "工作流发布/下线","workflow",   "publish"),
    ("sync:read",         "数据同步查看",   "sync",       "read"),
    ("sync:write",        "数据同步编辑",   "sync",       "write"),
    ("metadata:read",     "数据资产查看",   "metadata",   "read"),
    ("metadata:write",    "数据资产编辑",   "metadata",   "write"),
    ("monitor:read",      "系统监控查看",   "monitor",    "read"),
    ("monitor:write",     "监控规则编辑",   "monitor",    "write"),
]

_BUILTIN_ROLES = {
    "admin": {
        "name": "管理员",
        "description": "拥有所有权限",
        "permissions": [p[0] for p in _BUILTIN_PERMISSIONS],
    },
    "developer": {
        "name": "开发者",
        "description": "可管理数据源、组件、工作流、数据同步",
        "permissions": [
            "datasource:read", "datasource:write",
            "component:read", "component:create", "component:write", "component:publish",
            "workflow:read", "workflow:create", "workflow:write", "workflow:publish",
            "sync:read", "sync:write",
            "metadata:read", "metadata:write", "monitor:read", "monitor:write",
        ],
    },
    "analyst": {
        "name": "分析师",
        "description": "可查看数据资产和运行实例",
        "permissions": ["metadata:read", "monitor:read", "workflow:read", "component:read"],
    },
    "viewer": {
        "name": "只读用户",
        "description": "只能查看数据资产",
        "permissions": ["metadata:read"],
    },
}


def _seed_roles_and_permissions():
    from app.models.role import SysRole, SysPermission, SysRolePermission
    db = SessionLocal()
    try:
        for code, name, resource_type, action in _BUILTIN_PERMISSIONS:
            if not db.query(SysPermission).filter(SysPermission.code == code).first():
                db.add(SysPermission(code=code, name=name, resource_type=resource_type, action=action))
        db.flush()

        for role_code, role_info in _BUILTIN_ROLES.items():
            role = db.query(SysRole).filter(SysRole.code == role_code).first()
            if not role:
                role = SysRole(
                    code=role_code,
                    name=role_info["name"],
                    description=role_info["description"],
                    is_system=True,
                )
                db.add(role)
                db.flush()

            existing_perm_ids = {
                rp.permission_id
                for rp in db.query(SysRolePermission).filter(SysRolePermission.role_id == role.id).all()
            }
            for perm_code in role_info["permissions"]:
                perm = db.query(SysPermission).filter(SysPermission.code == perm_code).first()
                if perm and perm.id not in existing_perm_ids:
                    db.add(SysRolePermission(role_id=role.id, permission_id=perm.id))

        db.commit()
    finally:
        db.close()


_seed_roles_and_permissions()


# 确保管理员账号存在并关联 RBAC admin 角色
def _ensure_admin():
    from app.models.user import SysUser
    from app.models.role import SysRole, SysUserRole
    db = SessionLocal()
    try:
        admin = db.query(SysUser).filter(SysUser.username == "admin").first()
        if not admin:
            admin = SysUser(
                username="admin",
                password=hash_password(settings.ADMIN_INIT_PASSWORD),
                real_name="系统管理员",
                role="admin",
                status=1,
            )
            db.add(admin)
            db.flush()

        # 确保 admin 用户关联了 RBAC admin 角色
        admin_role = db.query(SysRole).filter(SysRole.code == "admin").first()
        if admin_role:
            exists = db.query(SysUserRole).filter(
                SysUserRole.user_id == admin.id,
                SysUserRole.role_id == admin_role.id,
            ).first()
            if not exists:
                db.add(SysUserRole(user_id=admin.id, role_id=admin_role.id))

        # 保持 legacy role 字段与 RBAC 一致
        if admin.role != "admin":
            admin.role = "admin"
        if admin.status != 1:
            admin.status = 1

        db.commit()
    finally:
        db.close()


def _ensure_default_project():
    from app.api.project import ensure_default_project
    db = SessionLocal()
    try:
        ensure_default_project(db)
    finally:
        db.close()


_ensure_admin()
_ensure_default_project()

app = FastAPI(
    title="数据中台 MVP",
    description="金融行业离线数据中台统一门户 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(datasources.router, prefix="/api")
app.include_router(sync_tasks.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ds_proxy.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(component.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(metadata.router, prefix="/api")
app.include_router(project.router, prefix="/api")

from app.api import alert_rules
app.include_router(alert_rules.router, prefix="/api")

from app.api import word_roots
app.include_router(word_roots.router, prefix="/api")

from app.api import admin
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "portal-backend"}
