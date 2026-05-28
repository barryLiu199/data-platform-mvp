"""
Application bootstrap: DDL creation, schema migrations, and seed data.

This module is called ONCE during application startup (via lifespan event),
NOT at import time. This allows:
- Tests to import app modules without triggering DB writes
- Multi-worker deployments to use a startup lock (future: Redis SETNX)
- CLI invocation for standalone migration/seed operations
"""
import logging
from sqlalchemy.orm import Session
from app.core.database import engine, Base, SessionLocal
from app.core.config import settings
from app.core.security import hash_password
from app.core.migrations import run_all_migrations

logger = logging.getLogger(__name__)

# ─── Seed data: 4 built-in roles + permissions ──────────────────────────────

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


def _seed_roles_and_permissions(db: Session):
    from app.models.role import SysRole, SysPermission, SysRolePermission

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


def _ensure_admin(db: Session):
    from app.models.user import SysUser
    from app.models.role import SysRole, SysUserRole

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

    admin_role = db.query(SysRole).filter(SysRole.code == "admin").first()
    if admin_role:
        exists = db.query(SysUserRole).filter(
            SysUserRole.user_id == admin.id,
            SysUserRole.role_id == admin_role.id,
        ).first()
        if not exists:
            db.add(SysUserRole(user_id=admin.id, role_id=admin_role.id))

    if admin.role != "admin":
        admin.role = "admin"
    if admin.status != 1:
        admin.status = 1


def _ensure_default_project(db: Session):
    from app.api.project import ensure_default_project
    ensure_default_project(db)


def bootstrap():
    """
    Run all startup tasks: DDL, migrations, seed data, reaper.
    Idempotent — safe to call multiple times.
    """
    # 1. Create tables from SQLAlchemy models
    # Import all models to register them with Base.metadata
    import app.models.component_folder  # noqa: F401
    import app.models.role  # noqa: F401
    import app.models.resource_access  # noqa: F401
    import app.models.oauth_config  # noqa: F401
    import app.models.sys_config  # noqa: F401
    import app.models.sys_notify_channel  # noqa: F401
    import app.models.lineage  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("DDL: tables created/verified")

    # 2. Run incremental schema migrations
    run_all_migrations()
    logger.info("Migrations: completed")

    # 3. Seed roles, permissions, admin user, default project
    db = SessionLocal()
    try:
        _seed_roles_and_permissions(db)
        _ensure_admin(db)
        _ensure_default_project(db)
        db.commit()
        logger.info("Seed data: roles + admin + default project ensured")
    finally:
        db.close()

    # 4. Reaper: 恢复 running 状态的 backfill 任务的状态同步
    from app.api.backfill import reap_stale_tasks
    try:
        reap_stale_tasks()
    except Exception:
        logger.exception("Backfill reaper 启动失败")
