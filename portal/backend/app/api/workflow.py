from typing import Optional, List, Dict, Any
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import get_accessible_ids, check_resource_permission, require_permission
from app.core.ds_client import get_ds_client
from app.core.workflow_publisher import WorkflowPublisher
from app.models.workflow import Workflow, WorkflowVersion
from app.models.component import Component
from app.models.user import SysUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["工作流"])


# ===== 状态常量 =====
STATUS_DRAFT = "draft"
STATUS_TESTED = "tested"
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"

EDITABLE_STATUSES = {STATUS_DRAFT, STATUS_TESTED, STATUS_OFFLINE}
DELETABLE_STATUSES = {STATUS_DRAFT, STATUS_OFFLINE}


# ===== Schemas =====
class WorkflowStep(BaseModel):
    component_id: int
    name: Optional[str] = None

class DagNode(BaseModel):
    id: str
    component_id: int
    name: Optional[str] = None
    position: Dict[str, float]  # {x, y}
    skip: bool = False

class DagEdge(BaseModel):
    id: str
    source: str
    target: str

class DagPayload(BaseModel):
    nodes: List[DagNode] = Field(default_factory=list)
    edges: List[DagEdge] = Field(default_factory=list)

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_id: Optional[int] = None
    steps: List[WorkflowStep] = Field(default_factory=list)
    dag: Optional[DagPayload] = None
    cron_expression: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = Field(default=3, ge=1, le=3)
    params: Optional[List[dict]] = None

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[int] = None
    steps: Optional[List[WorkflowStep]] = None
    dag: Optional[DagPayload] = None
    cron_expression: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    params: Optional[List[dict]] = None


def _serialize(w: Workflow, db: Session) -> dict:
    """序列化 workflow,steps 中带上 component 详情"""
    steps = w.steps_json or []
    # 补充 component 详情
    comp_ids = [s.get("component_id") for s in steps if s.get("component_id")]
    comp_map = {}
    if comp_ids:
        comps = db.query(Component).filter(Component.id.in_(comp_ids)).all()
        comp_map = {c.id: c for c in comps}
    enriched_steps = []
    for idx, s in enumerate(steps):
        cid = s.get("component_id")
        c = comp_map.get(cid)
        enriched_steps.append({
            "order": idx,
            "component_id": cid,
            "name": s.get("name") or (c.name if c else f"step_{idx}"),
            "component_name": c.name if c else None,
            "component_type": c.type if c else None,
            "component_status": c.status if c else None,
        })
    # 计算下次执行时间
    next_fire_time = None
    if w.cron_expression:
        try:
            from croniter import croniter
            from datetime import datetime
            cron_expr = w.cron_expression.strip()
            # DS 用 6 段 CRON（含秒），croniter 只支持 5 段，去掉第一段秒
            parts = cron_expr.split()
            if len(parts) == 6:
                cron_expr = ' '.join(parts[1:])
            # 替换 ? 为 * (DS 用 ? 表示不指定)
            cron_expr = cron_expr.replace('?', '*')
            cron = croniter(cron_expr, datetime.now())
            next_fire_time = str(cron.get_next(datetime))
        except Exception:
            pass
    # 把 component type 补进 dag 节点，前端渲染节点颜色/样式依赖此字段
    dag = w.dag_json
    if dag and dag.get("nodes"):
        dag_comp_ids = [n.get("component_id") for n in dag["nodes"] if n.get("component_id")]
        if dag_comp_ids:
            dag_comps = {c.id: c for c in db.query(Component).filter(Component.id.in_(dag_comp_ids)).all()}
        else:
            dag_comps = {}
        enriched_nodes = [
            {**n, "type": dag_comps[n["component_id"]].type if n.get("component_id") in dag_comps else n.get("type", "sql")}
            for n in dag["nodes"]
        ]
        dag = {**dag, "nodes": enriched_nodes}
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "tags": w.tags or [],
        "project_id": w.project_id,
        "steps": enriched_steps,
        "dag": dag,
        "cron_expression": w.cron_expression,
        "schedule_status": w.schedule_status,
        "status": w.status,
        "version": w.version,
        "priority": w.priority or 3,
        "params": w.params_json or [],
        "last_run_status": w.last_run_status,
        "last_run_time": str(w.last_run_time) if w.last_run_time else None,
        "last_run_duration": w.last_run_duration,
        "next_fire_time": next_fire_time,
        "ds_process_code": w.ds_process_code,
        "ds_schedule_id": w.ds_schedule_id,
        "created_at": str(w.created_at) if w.created_at else None,
        "updated_at": str(w.updated_at) if w.updated_at else None,
    }


def _get_or_404(db: Session, wf_id: int) -> Workflow:
    w = db.query(Workflow).filter(Workflow.id == wf_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return w


def _validate_steps(db: Session, steps: List[WorkflowStep]) -> List[Dict[str, Any]]:
    """校验所有 component 存在且发布,返回 steps_json 数据"""
    if not steps:
        return []
    comp_ids = [s.component_id for s in steps]
    comps = db.query(Component).filter(Component.id.in_(comp_ids)).all()
    comp_map = {c.id: c for c in comps}
    out = []
    for s in steps:
        c = comp_map.get(s.component_id)
        if not c:
            raise HTTPException(status_code=400, detail=f"组件 {s.component_id} 不存在")
        out.append({"component_id": s.component_id, "name": s.name or c.name})
    return out




# ===== 运行信息同步 =====
@router.post("/sync-last-run")
async def sync_last_run(
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """批量从 DS 同步最近运行信息到 Portal 缓存字段"""
    from datetime import datetime
    workflows = db.query(Workflow).filter(
        Workflow.ds_process_code.isnot(None)
    ).all()
    if not workflows:
        return {"synced": 0}
    try:
        ds = get_ds_client()
        pc = await ds._discover_project()
        if not pc:
            return {"synced": 0, "error": "DS project unavailable"}
    except Exception:
        return {"synced": 0, "error": "DS unavailable"}

    synced = 0
    for w in workflows:
        try:
            inst = await ds.get(f"/projects/{pc}/process-instances", params={
                "pageNo": 1, "pageSize": 1,
                "processDefinitionCode": w.ds_process_code,
            })
            last = (inst or {}).get("totalList", [None])[0]
            if last:
                w.last_run_status = last.get("state")
                start_str = last.get("startTime")
                end_str = last.get("endTime")
                if start_str:
                    try:
                        w.last_run_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        w.last_run_time = None
                if start_str and end_str:
                    try:
                        fmt = "%Y-%m-%d %H:%M:%S"
                        w.last_run_duration = int(
                            (datetime.strptime(end_str, fmt) - datetime.strptime(start_str, fmt)).total_seconds()
                        )
                    except Exception:
                        pass
                synced += 1
        except Exception as e:
            logger.warning("sync workflow %s failed: %s", w.id, e)
            continue
    db.commit()

    # 触发告警规则检查
    alerted = 0
    try:
        from app.models.alert_rule import AlertRule
        from app.core.notifier import notify as do_notify
        rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()
        for w in workflows:
            if not w.last_run_status:
                continue
            for rule in rules:
                # 匹配监控对象
                if rule.target_type == "workflow" and rule.target_id != w.id:
                    continue
                # 检查触发条件
                triggered = False
                if rule.trigger_type == "failure" and w.last_run_status == "FAILURE":
                    triggered = True
                elif rule.trigger_type == "timeout" and rule.trigger_value:
                    if w.last_run_duration and w.last_run_duration > rule.trigger_value:
                        triggered = True
                if triggered:
                    event = {
                        "workflow_name": w.name,
                        "status": w.last_run_status,
                        "time": str(w.last_run_time) if w.last_run_time else "",
                        "duration": w.last_run_duration,
                    }
                    await do_notify(rule, event)
                    alerted += 1
    except Exception as e:
        logger.exception("alert notify dispatch failed: %s", e)

    return {"synced": synced, "alerted": alerted}
# ===== CRUD =====
@router.get("")
def list_workflows(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    q = db.query(Workflow)
    if keyword:
        q = q.filter(Workflow.name.contains(keyword))
    if status:
        q = q.filter(Workflow.status == status)
    if project_id is not None:
        if project_id == 0:
            q = q.filter((Workflow.project_id == None) | (Workflow.project_id == 0))
        else:
            q = q.filter(Workflow.project_id == project_id)
    if tag:
        # 先用 contains 粗筛，再在应用层精确匹配，避免 "日报" 误匹配 "日报表"
        q = q.filter(Workflow.tags.contains(f'"{tag}"'))
    if tag:
        # 应用层精确过滤（JSON contains 可能误匹配子串）
        candidate_ids = [w.id for w in q.with_entities(Workflow.id, Workflow.tags).all() if tag in (w.tags or [])]
        q = db.query(Workflow).filter(Workflow.id.in_(candidate_ids)) if candidate_ids else q.filter(False)

    # 资源级 ACL 过滤
    accessible = get_accessible_ids(db, current_user, "workflow", "read")
    if accessible is not None:
        q = q.filter(Workflow.id.in_(accessible)) if accessible else q.filter(False)

    total = q.count()
    items = q.order_by(Workflow.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 收集所有已使用的标签
    all_tags = set()
    for w in db.query(Workflow.tags).filter(Workflow.tags.isnot(None)).all():
        if w.tags:
            all_tags.update(w.tags)
    return {"total": total, "items": [_serialize(w, db) for w in items], "all_tags": sorted(all_tags)}


@router.post("")
def create_workflow(
    req: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:create")),
):
    steps_data = _validate_steps(db, req.steps)
    dag_data = None
    if req.dag and req.dag.nodes:
        dag_data = {"nodes": [n.model_dump() for n in req.dag.nodes], "edges": [e.model_dump() for e in req.dag.edges]}
        # 从 DAG 生成兼容的 steps_json（拓扑排序）
        steps_data = [{"component_id": n.component_id, "name": n.name} for n in req.dag.nodes if not n.skip]
    w = Workflow(
        name=req.name,
        description=req.description,
        tags=req.tags or [],
        project_id=req.project_id,
        steps_json=steps_data,
        dag_json=dag_data,
        cron_expression=req.cron_expression,
        schedule_status="OFFLINE",
        status=STATUS_DRAFT,
        version=1,
        priority=req.priority or 3,
        params_json=req.params or [],
        created_by=current_user.id,
    )
    db.add(w)
    db.flush()  # 获取 w.id

    # 自动授予创建者 admin 权限
    from app.models.resource_access import SysResourceAccess
    db.add(SysResourceAccess(
        resource_type="workflow",
        resource_id=w.id,
        subject_type="user",
        subject_id=current_user.id,
        permission="admin",
        granted_by=current_user.id,
    ))

    db.commit()
    db.refresh(w)
    return _serialize(w, db)


@router.get("/scheduled")
def list_scheduled_workflows(
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """返回所有配置了 cron 的工作流（调度任务页面用）"""
    q = db.query(Workflow).filter(
        Workflow.cron_expression.isnot(None),
        Workflow.cron_expression != "",
    ).order_by(Workflow.id.desc())

    # 资源级 ACL 过滤（与 list_workflows 保持一致）
    accessible = get_accessible_ids(db, current_user, "workflow", "read")
    if accessible is not None:
        q = q.filter(Workflow.id.in_(accessible)) if accessible else q.filter(False)

    items = q.all()
    result = []
    for w in items:
        item = _serialize(w, db)
        try:
            from croniter import croniter
            from datetime import datetime
            cron = croniter(w.cron_expression, datetime.now())
            item["next_fire_time"] = str(cron.get_next(datetime))
        except Exception:
            item["next_fire_time"] = None
        result.append(item)
    return {"items": result, "total": len(result)}


@router.get("/{wf_id}")
def get_workflow(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "read"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    return _serialize(w, db)


@router.put("/{wf_id}")
def update_workflow(
    wf_id: int,
    req: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"工作流状态 {w.status},只有 draft/tested 状态允许编辑;请先下线",
        )
    updates = req.model_dump(exclude_unset=True)
    structural_change = False
    if "name" in updates:
        w.name = updates["name"]
    if "description" in updates:
        w.description = updates["description"]
    if "project_id" in updates:
        w.project_id = updates["project_id"]
    if "tags" in updates:
        w.tags = updates["tags"] or []
    if "cron_expression" in updates:
        w.cron_expression = updates["cron_expression"]
    if "priority" in updates:
        w.priority = updates["priority"]
    if "params" in updates:
        w.params_json = updates["params"] or []
    if "steps" in updates:
        steps_data = _validate_steps(db, [WorkflowStep(**s) for s in updates["steps"]])
        w.steps_json = steps_data
        structural_change = True
    if "dag" in updates and updates["dag"]:
        dag_raw = updates["dag"]
        dag_data = {"nodes": dag_raw.get("nodes", []), "edges": dag_raw.get("edges", [])}
        # 校验所有非 skip 节点的 component_id 存在且有效
        comp_ids = [n["component_id"] for n in dag_data["nodes"] if not n.get("skip")]
        if comp_ids:
            found = {c.id for c in db.query(Component.id).filter(Component.id.in_(comp_ids)).all()}
            missing = [cid for cid in comp_ids if cid not in found]
            if missing:
                raise HTTPException(status_code=400, detail=f"以下组件不存在: {missing}")
        w.dag_json = dag_data
        # 同步 steps_json
        w.steps_json = [{"component_id": n["component_id"], "name": n.get("name")} for n in dag_data["nodes"] if not n.get("skip")]
        structural_change = True
    if structural_change:
        w.status = STATUS_DRAFT
        w.version = (w.version or 1) + 1
    db.commit()
    db.refresh(w)
    return _serialize(w, db)


@router.delete("/{wf_id}")
async def delete_workflow(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "admin"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status not in DELETABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"工作流状态 {w.status},只有 draft/offline 状态允许删除;请先下线",
        )
    # 先清理 DS 资源 (尽量,失败也继续删 Portal 记录)
    publisher = WorkflowPublisher(db, get_ds_client())
    await publisher.cleanup(w)
    from app.models.resource_access import SysResourceAccess
    db.query(SysResourceAccess).filter(
        SysResourceAccess.resource_type == "workflow",
        SysResourceAccess.resource_id == wf_id,
    ).delete()
    db.delete(w)
    db.commit()
    return {"message": "删除成功"}


# ===== 状态机操作 =====
@router.post("/{wf_id}/test")
def test_workflow(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    """测试工作流 — 检查所有 component 都已发布"""
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status not in {STATUS_DRAFT, STATUS_TESTED}:
        raise HTTPException(status_code=400, detail=f"状态 {w.status} 下不允许测试")
    # 从 DAG 或 steps 提取 component_id
    if w.dag_json and w.dag_json.get("nodes"):
        comp_ids = [n["component_id"] for n in w.dag_json["nodes"] if not n.get("skip")]
    else:
        steps = w.steps_json or []
        comp_ids = [s.get("component_id") for s in steps]
    if not comp_ids:
        raise HTTPException(status_code=400, detail="工作流为空,请先添加步骤")
    comps = db.query(Component).filter(Component.id.in_(comp_ids)).all()
    comp_map = {c.id: c for c in comps}
    unpublished = []
    for cid in comp_ids:
        c = comp_map.get(cid)
        if not c:
            unpublished.append(f"组件{cid}(不存在)")
        elif c.status != "online":
            unpublished.append(f"{c.name}(当前 {c.status})")
    if unpublished:
        raise HTTPException(
            status_code=400,
            detail=f"以下组件未上线,无法测试: {', '.join(unpublished)}",
        )
    # TODO Phase 5+: 实际触发 DS 试运行
    w.status = STATUS_TESTED
    db.commit()
    db.refresh(w)
    return {"message": "测试通过 (Phase 4 占位)", **_serialize(w, db)}


@router.post("/{wf_id}/publish")
async def publish_workflow(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:publish")),
):
    """发布工作流 — tested 才能发布,真正同步到 DS"""
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status != STATUS_TESTED:
        raise HTTPException(
            status_code=400,
            detail=f"只有 tested 状态可发布,当前 {w.status},请先测试",
        )
    publisher = WorkflowPublisher(db, get_ds_client())
    pd_code, schedule_id = await publisher.publish(w)
    w.ds_process_code = pd_code
    w.ds_schedule_id = schedule_id
    w.status = STATUS_ONLINE
    # 创建版本快照
    ver = WorkflowVersion(
        workflow_id=w.id,
        version=w.version,
        name=w.name,
        description=w.description,
        tags=w.tags,
        dag_json=w.dag_json,
        steps_json=w.steps_json,
        cron_expression=w.cron_expression,
        priority=w.priority,
        params_json=w.params_json,
        published_by=current_user.id,
    )
    db.add(ver)
    db.commit()
    db.refresh(w)
    return {"message": "已发布并同步到 DS", **_serialize(w, db)}


@router.post("/{wf_id}/offline")
async def offline_workflow(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:publish")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status != STATUS_ONLINE:
        raise HTTPException(status_code=400, detail=f"只有 online 状态可下线,当前 {w.status}")
    # 同步下线 DS 调度 + process definition
    publisher = WorkflowPublisher(db, get_ds_client())
    await publisher.unpublish(w)
    w.status = STATUS_OFFLINE
    w.schedule_status = "OFFLINE"
    db.commit()
    db.refresh(w)
    return {"message": "已下线 (DS 已同步)", **_serialize(w, db)}


class RunWorkflowRequest(BaseModel):
    params: Optional[Dict[str, str]] = None


@router.post("/{wf_id}/run")
async def run_workflow(
    wf_id: int,
    body: RunWorkflowRequest = RunWorkflowRequest(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    """手动运行工作流 — 通过 DS 触发"""
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status not in {STATUS_ONLINE, STATUS_TESTED}:
        raise HTTPException(status_code=400, detail=f"状态 {w.status} 下不允许运行,需先测试/发布")
    if not w.ds_process_code:
        raise HTTPException(status_code=400, detail="工作流未同步到 DS,请先发布")
    ds = get_ds_client()
    # 构造 startParams: "key1=val1,key2=val2"
    import json as _json
    start_params = ""
    if body.params:
        start_params = _json.dumps(body.params, ensure_ascii=False)
    result = await ds.start_process_instance(w.ds_process_code, start_params=start_params)
    if result is None:
        raise HTTPException(status_code=502, detail="DS 触发运行失败")
    return {
        "message": "已触发运行",
        "workflow_id": w.id,
        "ds_process_code": w.ds_process_code,
        "ds_response": result,
    }


# ===== 调度开关 =====
@router.post("/{wf_id}/schedule/online")
async def schedule_online(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:publish")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.status != STATUS_ONLINE:
        raise HTTPException(status_code=400, detail="工作流需先发布上线才能开启调度")
    if not w.cron_expression:
        raise HTTPException(status_code=400, detail="未配置 cron 表达式,请先编辑")
    if not w.ds_schedule_id:
        # 没有 schedule 就创建一个
        if not w.ds_process_code:
            raise HTTPException(status_code=400, detail="工作流未同步到 DS")
        ds = get_ds_client()
        sid = await ds.create_schedule(w.ds_process_code, w.cron_expression)
        if not sid:
            raise HTTPException(status_code=502, detail="DS 创建调度失败")
        w.ds_schedule_id = sid
    ds = get_ds_client()
    ok = await ds.schedule_online(w.ds_schedule_id)
    if not ok:
        raise HTTPException(status_code=502, detail="DS 上线调度失败")
    w.schedule_status = "ONLINE"
    db.commit()
    db.refresh(w)
    return {"message": "调度已开启", **_serialize(w, db)}


@router.post("/{wf_id}/schedule/offline")
async def schedule_offline(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:publish")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    if w.ds_schedule_id:
        publisher = WorkflowPublisher(db, get_ds_client())
        await publisher.schedule_off(w)
    w.schedule_status = "OFFLINE"
    db.commit()
    db.refresh(w)
    return {"message": "调度已关闭", **_serialize(w, db)}


@router.post("/cron-preview")
async def cron_preview(body: dict):
    """给定 CRON 表达式，返回未来 5 次执行时间"""
    from croniter import croniter
    from datetime import datetime as dt
    cron = body.get("cron_expression", "")
    if not cron or not cron.strip():
        return {"times": []}
    parts = cron.strip().split()
    if len(parts) == 6:
        parts = parts[1:]
    cron5 = " ".join(parts).replace("?", "*")
    try:
        ci = croniter(cron5, dt.now())
        times = [ci.get_next(dt).strftime("%Y-%m-%d %H:%M") for _ in range(5)]
    except Exception:
        return {"times": [], "error": "无效的 CRON 表达式"}
    return {"times": times}


# ===== 版本历史 =====
@router.get("/{wf_id}/versions")
def list_versions(
    wf_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "read"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    versions = db.query(WorkflowVersion).filter(
        WorkflowVersion.workflow_id == wf_id
    ).order_by(WorkflowVersion.id.desc()).all()
    # 获取发布人名称
    user_ids = {v.published_by for v in versions if v.published_by}
    user_map = {}
    if user_ids:
        users = db.query(SysUser).filter(SysUser.id.in_(user_ids)).all()
        user_map = {u.id: u.real_name or u.username for u in users}
    return {
        "items": [
            {
                "id": v.id,
                "version": v.version,
                "name": v.name,
                "comment": v.comment,
                "published_by": v.published_by,
                "published_by_name": user_map.get(v.published_by, ""),
                "published_at": str(v.published_at) if v.published_at else None,
            }
            for v in versions
        ]
    }


@router.get("/{wf_id}/versions/{ver_id}")
def get_version(
    wf_id: int,
    ver_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "read"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    v = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == ver_id, WorkflowVersion.workflow_id == wf_id
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {
        "id": v.id,
        "version": v.version,
        "name": v.name,
        "description": v.description,
        "tags": v.tags,
        "dag_json": v.dag_json,
        "steps_json": v.steps_json,
        "cron_expression": v.cron_expression,
        "priority": v.priority,
        "comment": v.comment,
        "published_by": v.published_by,
        "published_at": str(v.published_at) if v.published_at else None,
    }


@router.post("/{wf_id}/versions/{ver_id}/rollback")
def rollback_version(
    wf_id: int,
    ver_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    w = _get_or_404(db, wf_id)
    if not check_resource_permission(db, current_user, "workflow", wf_id, "write"):
        raise HTTPException(status_code=404, detail="工作流不存在")
    v = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == ver_id, WorkflowVersion.workflow_id == wf_id
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    w.name = v.name
    w.description = v.description
    w.tags = v.tags
    w.dag_json = v.dag_json
    w.steps_json = v.steps_json
    w.cron_expression = v.cron_expression
    w.priority = v.priority
    w.version = (w.version or 1) + 1
    w.status = STATUS_DRAFT
    db.commit()
    db.refresh(w)
    return {"message": f"已回滚到 v{v.version}", **_serialize(w, db)}
