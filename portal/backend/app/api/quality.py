"""数据质量 API — 规则 CRUD、执行、结果查询、统计"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.core.quality_engine import execute_rule, preview_sql
from app.core.validators import IdentifierError, validate_sql_identifier
from app.models.quality import QualityRule, QualityRuleTemplate, QualityCheckResult
from app.models.datasource import DataSource
from app.models.user import SysUser

router = APIRouter(prefix="/quality", tags=["数据质量"])


# 配置中需要校验为 SQL 标识符的字段名
_CONFIG_IDENT_FIELDS = (
    "field", "date_field",
    "dict_table", "dict_field",
    "table_a", "table_b",
)
# 配置中数组型标识符字段：每个元素都要校验
_CONFIG_IDENT_ARRAY_FIELDS = ("fields",)


def _validate_config_identifiers(config: dict) -> dict:
    """对 config 内的标识符类字段统一校验。custom_sql 模板的 sql 字段不在这里校验。"""
    if not isinstance(config, dict):
        return config
    for key in _CONFIG_IDENT_FIELDS:
        v = config.get(key)
        if v:
            try:
                validate_sql_identifier(v, field=f"config.{key}")
            except IdentifierError as e:
                raise ValueError(str(e))
    for key in _CONFIG_IDENT_ARRAY_FIELDS:
        arr = config.get(key)
        if isinstance(arr, list):
            for i, v in enumerate(arr):
                if v:
                    try:
                        validate_sql_identifier(v, field=f"config.{key}[{i}]")
                    except IdentifierError as e:
                        raise ValueError(str(e))
    # cross_table_check: join_keys / compare_fields 是 [{a,b}, ...]
    for key in ("join_keys", "compare_fields"):
        arr = config.get(key)
        if isinstance(arr, list):
            for i, item in enumerate(arr):
                if not isinstance(item, dict):
                    continue
                for sub in ("a", "b"):
                    v = item.get(sub)
                    if v:
                        try:
                            validate_sql_identifier(v, field=f"config.{key}[{i}].{sub}")
                        except IdentifierError as e:
                            raise ValueError(str(e))
    return config


# ===== Schemas =====

class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    template_code: str
    datasource_id: Optional[int] = None
    table_name: Optional[str] = Field(None, max_length=256)
    column_name: Optional[str] = Field(None, max_length=256)
    config: dict = Field(default_factory=dict)
    severity: str = Field(default="warning")
    trigger_type: str = Field(default="manual")
    trigger_workflow_id: Optional[int] = None
    notify_enabled: bool = False
    notify_channel_ids: Optional[list] = None

    @field_validator("table_name", "column_name")
    @classmethod
    def _check_ident(cls, v):
        if v is not None and v != "":
            try:
                validate_sql_identifier(v, field="name")
            except IdentifierError as e:
                raise ValueError(str(e))
        return v

    @field_validator("config")
    @classmethod
    def _check_config(cls, v):
        return _validate_config_identifiers(v)


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    datasource_id: Optional[int] = None
    table_name: Optional[str] = Field(None, max_length=256)
    column_name: Optional[str] = Field(None, max_length=256)
    config: Optional[dict] = None
    severity: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_workflow_id: Optional[int] = None
    notify_enabled: Optional[bool] = None
    notify_channel_ids: Optional[list] = None

    @field_validator("table_name", "column_name")
    @classmethod
    def _check_ident(cls, v):
        if v is not None and v != "":
            try:
                validate_sql_identifier(v, field="name")
            except IdentifierError as e:
                raise ValueError(str(e))
        return v

    @field_validator("config")
    @classmethod
    def _check_config(cls, v):
        if v is None:
            return v
        return _validate_config_identifiers(v)


# ===== Templates =====

@router.get("/templates")
def list_templates(db: Session = Depends(get_db), _=Depends(get_current_user)):
    templates = (
        db.query(QualityRuleTemplate)
        .order_by(QualityRuleTemplate.display_order)
        .all()
    )
    return [
        {
            "id": t.id,
            "code": t.code,
            "name": t.name,
            "category": t.category,
            "level": t.level,
            "description": t.description,
            "config_schema": t.config_schema,
            "display_order": t.display_order,
        }
        for t in templates
    ]


# ===== Rules CRUD =====

@router.get("/rules")
def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    template_code: Optional[str] = None,
    datasource_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(QualityRule)
    if template_code:
        q = q.filter(QualityRule.template_code == template_code)
    if datasource_id:
        q = q.filter(QualityRule.datasource_id == datasource_id)
    if status:
        q = q.filter(QualityRule.last_check_status == status)
    if keyword:
        q = q.filter(QualityRule.name.contains(keyword))

    total = q.count()
    rules = q.order_by(QualityRule.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    ds_ids = {r.datasource_id for r in rules if r.datasource_id}
    ds_map = {}
    if ds_ids:
        dss = db.query(DataSource).filter(DataSource.id.in_(ds_ids)).all()
        ds_map = {d.id: d.name for d in dss}

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "template_code": r.template_code,
                "datasource_id": r.datasource_id,
                "datasource_name": ds_map.get(r.datasource_id, ""),
                "table_name": r.table_name,
                "column_name": r.column_name,
                "severity": r.severity,
                "trigger_type": r.trigger_type,
                "trigger_workflow_id": r.trigger_workflow_id,
                "notify_enabled": r.notify_enabled,
                "notify_channel_ids": r.notify_channel_ids,
                "enabled": r.enabled,
                "last_check_time": r.last_check_time.isoformat() if r.last_check_time else None,
                "last_check_status": r.last_check_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ],
    }


@router.get("/rules/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")

    results = (
        db.query(QualityCheckResult)
        .filter(QualityCheckResult.rule_id == rule_id)
        .order_by(QualityCheckResult.check_date.desc())
        .limit(10)
        .all()
    )

    ds_name = ""
    if rule.datasource_id:
        ds = db.query(DataSource).get(rule.datasource_id)
        ds_name = ds.name if ds else ""

    return {
        "id": rule.id,
        "name": rule.name,
        "template_code": rule.template_code,
        "datasource_id": rule.datasource_id,
        "datasource_name": ds_name,
        "table_name": rule.table_name,
        "column_name": rule.column_name,
        "config": rule.config,
        "severity": rule.severity,
        "trigger_type": rule.trigger_type,
        "trigger_workflow_id": rule.trigger_workflow_id,
        "notify_enabled": rule.notify_enabled,
        "notify_channel_ids": rule.notify_channel_ids,
        "enabled": rule.enabled,
        "last_check_time": rule.last_check_time.isoformat() if rule.last_check_time else None,
        "last_check_status": rule.last_check_status,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "recent_results": [
            {
                "id": r.id,
                "check_date": r.check_date.isoformat(),
                "status": r.status,
                "actual_value": r.actual_value,
                "expected_value": r.expected_value,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }


@router.post("/rules")
def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_permission("quality:write")),
):
    tpl = db.query(QualityRuleTemplate).filter(QualityRuleTemplate.code == body.template_code).first()
    if not tpl:
        raise HTTPException(400, f"模板 {body.template_code} 不存在")

    rule = QualityRule(
        name=body.name,
        template_code=body.template_code,
        datasource_id=body.datasource_id,
        table_name=body.table_name,
        column_name=body.column_name,
        config=body.config,
        severity=body.severity,
        trigger_type=body.trigger_type,
        trigger_workflow_id=body.trigger_workflow_id,
        notify_enabled=body.notify_enabled,
        notify_channel_ids=body.notify_channel_ids,
        created_by=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "message": "创建成功"}


@router.put("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")

    for field, value in body.dict(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    return {"message": "更新成功"}


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    db.delete(rule)
    db.commit()
    return {"message": "删除成功"}


@router.patch("/rules/{rule_id}/toggle")
def toggle_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    rule.enabled = not rule.enabled
    db.commit()
    return {"enabled": rule.enabled}


# ===== Execution =====

@router.post("/rules/{rule_id}/execute")
def execute_single(
    rule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    if not rule.enabled:
        raise HTTPException(400, "规则已禁用")
    background_tasks.add_task(execute_rule, rule_id, "manual")
    return {"message": "已提交执行"}


@router.post("/rules/batch-execute")
def batch_execute(
    body: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    rule_ids = body.get("rule_ids", [])
    if not rule_ids:
        rules = db.query(QualityRule).filter(QualityRule.enabled == True).all()
        rule_ids = [r.id for r in rules]
    for rid in rule_ids:
        background_tasks.add_task(execute_rule, rid, "manual")
    return {"message": f"已提交 {len(rule_ids)} 条规则"}


@router.post("/execute-by-table")
def execute_by_table(
    body: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(require_permission("quality:write")),
):
    ds_id = body.get("datasource_id")
    table = body.get("table_name")
    if not ds_id or not table:
        raise HTTPException(400, "需要 datasource_id 和 table_name")
    rules = (
        db.query(QualityRule)
        .filter(
            QualityRule.datasource_id == ds_id,
            QualityRule.table_name == table,
            QualityRule.enabled == True,
        )
        .all()
    )
    for r in rules:
        background_tasks.add_task(execute_rule, r.id, "manual")
    return {"message": f"已提交 {len(rules)} 条规则"}


@router.post("/rules/preview-sql")
def rule_preview_sql(
    body: dict,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    rule_id = body.get("rule_id")
    if not rule_id:
        raise HTTPException(400, "需要 rule_id")
    result = preview_sql(rule_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ===== Results =====

@router.get("/results")
def list_results(
    rule_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(QualityCheckResult)
    if rule_id:
        q = q.filter(QualityCheckResult.rule_id == rule_id)
    if status:
        q = q.filter(QualityCheckResult.status == status)

    total = q.count()
    items = (
        q.order_by(QualityCheckResult.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "check_date": r.check_date.isoformat(),
                "status": r.status,
                "actual_value": r.actual_value,
                "expected_value": r.expected_value,
                "detail": r.detail,
                "executed_sql": r.executed_sql,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
    }


@router.get("/results/trend")
def result_trend(
    rule_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    since = date.today() - timedelta(days=days)
    results = (
        db.query(QualityCheckResult)
        .filter(
            QualityCheckResult.rule_id == rule_id,
            QualityCheckResult.check_date >= since,
        )
        .order_by(QualityCheckResult.check_date)
        .all()
    )
    return [
        {
            "date": r.check_date.isoformat(),
            "status": r.status,
            "actual_value": r.actual_value,
            "duration_ms": r.duration_ms,
        }
        for r in results
    ]


@router.get("/stats")
def quality_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    total_rules = db.query(func.count(QualityRule.id)).scalar() or 0
    enabled_rules = (
        db.query(func.count(QualityRule.id))
        .filter(QualityRule.enabled == True)
        .scalar()
        or 0
    )

    today = date.today()
    today_results = (
        db.query(QualityCheckResult)
        .filter(QualityCheckResult.check_date == today)
        .all()
    )
    today_pass = sum(1 for r in today_results if r.status == "pass")
    today_fail = sum(1 for r in today_results if r.status == "fail")
    today_error = sum(1 for r in today_results if r.status == "error")
    pass_rate = round(today_pass / len(today_results) * 100, 1) if today_results else 0

    return {
        "total_rules": total_rules,
        "enabled_rules": enabled_rules,
        "today_pass": today_pass,
        "today_fail": today_fail,
        "today_error": today_error,
        "pass_rate": pass_rate,
    }


# ===== Metadata Quality (for DataAssets tab) =====

@router.get("/metadata/quality")
def metadata_quality(
    datasource_id: int,
    table_name: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    rules = (
        db.query(QualityRule)
        .filter(
            QualityRule.datasource_id == datasource_id,
            QualityRule.table_name == table_name,
        )
        .all()
    )

    result = []
    for r in rules:
        latest = (
            db.query(QualityCheckResult)
            .filter(QualityCheckResult.rule_id == r.id)
            .order_by(QualityCheckResult.check_date.desc())
            .first()
        )
        result.append({
            "rule_id": r.id,
            "rule_name": r.name,
            "template_code": r.template_code,
            "severity": r.severity,
            "enabled": r.enabled,
            "last_check_status": r.last_check_status,
            "last_check_time": r.last_check_time.isoformat() if r.last_check_time else None,
            "latest_result": {
                "check_date": latest.check_date.isoformat(),
                "status": latest.status,
                "actual_value": latest.actual_value,
                "duration_ms": latest.duration_ms,
            } if latest else None,
        })
    return result
