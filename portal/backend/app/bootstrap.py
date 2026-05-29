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
    ("quality:read",      "数据质量查看",   "quality",    "read"),
    ("quality:write",     "数据质量编辑",   "quality",    "write"),
    ("lineage:write",     "血缘编辑/手工补登","lineage",   "write"),
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
            "quality:read", "quality:write",
            "lineage:write",
        ],
    },
    "analyst": {
        "name": "分析师",
        "description": "可查看数据资产和运行实例",
        "permissions": ["metadata:read", "monitor:read", "workflow:read", "component:read", "quality:read"],
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


def _seed_quality_templates(db: Session):
    from app.models.quality import QualityRuleTemplate
    import json

    TEMPLATES = [
        {
            "code": "cross_table_check", "name": "跨表核对", "category": "accuracy",
            "level": "table", "display_order": 1,
            "description": "比较两张表的关联字段值是否一致（支持跨数据源）",
            "config_schema": json.dumps({
                "ds_id_a": {"type": "integer", "label": "数据源A", "required": True},
                "table_a": {"type": "string", "label": "表A", "required": True},
                "ds_id_b": {"type": "integer", "label": "数据源B", "required": True},
                "table_b": {"type": "string", "label": "表B", "required": True},
                "join_keys": {"type": "array", "label": "关联键", "required": True,
                              "items": {"a": "string", "b": "string"}},
                "compare_fields": {"type": "array", "label": "比对字段", "required": True,
                                   "items": {"a": "string", "b": "string"}},
                "tolerance": {"type": "number", "label": "容差", "default": 0},
            }),
        },
        {
            "code": "uniqueness", "name": "唯一性检查", "category": "consistency",
            "level": "field", "display_order": 2,
            "description": "检查字段（或组合字段）值是否唯一，无重复",
            "config_schema": json.dumps({
                "fields": {"type": "array", "label": "检查字段", "required": True,
                           "items": {"type": "string"}},
            }),
        },
        {
            "code": "dict_ref", "name": "字典引用检查", "category": "consistency",
            "level": "field", "display_order": 3,
            "description": "检查字段值是否都在字典表中存在",
            "config_schema": json.dumps({
                "field": {"type": "string", "label": "检查字段", "required": True},
                "dict_ds_id": {"type": "integer", "label": "字典数据源"},
                "dict_table": {"type": "string", "label": "字典表", "required": True},
                "dict_field": {"type": "string", "label": "字典字段", "required": True},
            }),
        },
        {
            "code": "timeliness", "name": "及时性检查", "category": "timeliness",
            "level": "table", "display_order": 4,
            "description": "检查数据是否按时到达（指定日期是否有数据）",
            "config_schema": json.dumps({
                "date_field": {"type": "string", "label": "日期字段", "required": True},
                "expected_date": {"type": "string", "label": "预期日期",
                                  "default": "today", "description": "today 或 yyyy-mm-dd"},
            }),
        },
        {
            "code": "not_null", "name": "非空检查", "category": "completeness",
            "level": "field", "display_order": 5,
            "description": "检查字段是否存在 NULL 值",
            "config_schema": json.dumps({
                "field": {"type": "string", "label": "检查字段", "required": True},
            }),
        },
        {
            "code": "row_count", "name": "表行数波动", "category": "completeness",
            "level": "table", "display_order": 6,
            "description": "检查表行数与上次相比的波动率是否超出阈值",
            "config_schema": json.dumps({
                "threshold_pct": {"type": "number", "label": "波动率阈值(%)", "default": 50},
            }),
        },
        {
            "code": "null_rate", "name": "字段空值率", "category": "completeness",
            "level": "field", "display_order": 7,
            "description": "检查字段空值占比是否超出阈值",
            "config_schema": json.dumps({
                "field": {"type": "string", "label": "检查字段", "required": True},
                "threshold_pct": {"type": "number", "label": "空值率阈值(%)", "default": 5},
            }),
        },
        {
            "code": "value_range", "name": "值域范围检查", "category": "accuracy",
            "level": "field", "display_order": 8,
            "description": "检查数值字段是否在指定范围内",
            "config_schema": json.dumps({
                "field": {"type": "string", "label": "检查字段", "required": True},
                "min_value": {"type": "number", "label": "最小值"},
                "max_value": {"type": "number", "label": "最大值"},
            }),
        },
        {
            "code": "regex_match", "name": "正则匹配", "category": "accuracy",
            "level": "field", "display_order": 9,
            "description": "检查字段值是否匹配正则表达式（如手机号、证件号格式）",
            "config_schema": json.dumps({
                "field": {"type": "string", "label": "检查字段", "required": True},
                "pattern": {"type": "string", "label": "正则表达式", "required": True},
            }),
        },
        {
            "code": "custom_sql", "name": "自定义SQL", "category": "accuracy",
            "level": "any", "display_order": 10,
            "description": "自定义 SQL 查询，返回单行单列数值，按阈值判定",
            "config_schema": json.dumps({
                "sql": {"type": "string", "label": "SQL", "required": True, "multiline": True},
                "operator": {"type": "string", "label": "比较方式", "required": True,
                             "enum": ["=", "!=", ">", ">=", "<", "<="]},
                "threshold": {"type": "number", "label": "阈值", "required": True},
            }),
        },
    ]

    for t in TEMPLATES:
        if not db.query(QualityRuleTemplate).filter(QualityRuleTemplate.code == t["code"]).first():
            db.add(QualityRuleTemplate(**t))


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
    import app.models.column_lineage  # noqa: F401
    import app.models.quality  # noqa: F401

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
        _seed_quality_templates(db)
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
