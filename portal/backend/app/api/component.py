import time
import subprocess
import tempfile
import os
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.component import Component
from app.models.user import SysUser

router = APIRouter(prefix="/components", tags=["组件"])

# ===== 类型与状态常量 =====
VALID_TYPES = {"sql", "python", "shell", "datax"}

# 状态定义
STATUS_DRAFT = "draft"
STATUS_DEVELOPING = "developing"
STATUS_TESTING = "testing"
STATUS_REVIEWING = "reviewing"
STATUS_TESTED = "tested"
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_PAUSED = "paused"
STATUS_DEPRECATED = "deprecated"
STATUS_ARCHIVED = "archived"

# 所有有效状态
VALID_STATUSES = {
    STATUS_DRAFT, STATUS_DEVELOPING, STATUS_TESTING,
    STATUS_REVIEWING, STATUS_TESTED, STATUS_ONLINE,
    STATUS_OFFLINE, STATUS_PAUSED, STATUS_DEPRECATED, STATUS_ARCHIVED,
}

# 用户可手动设置的状态（不包括自动状态 draft/online）
MANUAL_STATUSES = {
    STATUS_DEVELOPING, STATUS_TESTING, STATUS_REVIEWING,
    STATUS_TESTED, STATUS_OFFLINE, STATUS_PAUSED,
    STATUS_DEPRECATED, STATUS_ARCHIVED,
}

# 自动流转状态
AUTO_STATUSES = {STATUS_DRAFT, STATUS_ONLINE}

# 允许编辑/删除的状态
EDITABLE_STATUSES = {STATUS_DRAFT, STATUS_DEVELOPING, STATUS_TESTING, STATUS_REVIEWING, STATUS_TESTED, STATUS_OFFLINE, STATUS_PAUSED, STATUS_DEPRECATED}
DELETABLE_STATUSES = {STATUS_DRAFT, STATUS_OFFLINE, STATUS_DEPRECATED, STATUS_ARCHIVED}

# 状态显示名
STATUS_LABELS = {
    STATUS_DRAFT: "草稿",
    STATUS_DEVELOPING: "开发中",
    STATUS_TESTING: "测试中",
    STATUS_REVIEWING: "审核中",
    STATUS_TESTED: "已测试",
    STATUS_ONLINE: "已上线",
    STATUS_OFFLINE: "已下线",
    STATUS_PAUSED: "已暂停",
    STATUS_DEPRECATED: "已废弃",
    STATUS_ARCHIVED: "已归档",
}

# 状态颜色
STATUS_COLORS = {
    STATUS_DRAFT: "#86909C",
    STATUS_DEVELOPING: "#2B5AED",
    STATUS_TESTING: "#FF7D00",
    STATUS_REVIEWING: "#14B8A6",
    STATUS_TESTED: "#A3C644",
    STATUS_ONLINE: "#00B42A",
    STATUS_OFFLINE: "#C9CDD4",
    STATUS_PAUSED: "#F53F3F",
    STATUS_DEPRECATED: "#6B7280",
    STATUS_ARCHIVED: "#722ED1",
}

# 状态流转规则: {当前状态: [允许的目标状态]}
STATUS_TRANSITIONS = {
    STATUS_DRAFT: [STATUS_DEVELOPING, STATUS_TESTING, STATUS_DEPRECATED, STATUS_ARCHIVED],
    STATUS_DEVELOPING: [STATUS_TESTING, STATUS_PAUSED, STATUS_DEPRECATED],
    STATUS_TESTING: [STATUS_REVIEWING, STATUS_TESTED, STATUS_PAUSED, STATUS_DEPRECATED],
    STATUS_REVIEWING: [STATUS_TESTED, STATUS_PAUSED, STATUS_DEVELOPING],
    STATUS_TESTED: [STATUS_ONLINE, STATUS_PAUSED, STATUS_TESTING],  # online 通过发布操作
    STATUS_ONLINE: [STATUS_OFFLINE, STATUS_PAUSED],
    STATUS_OFFLINE: [STATUS_ONLINE, STATUS_ARCHIVED, STATUS_PAUSED, STATUS_DEVELOPING],
    STATUS_PAUSED: [],  # 恢复时回到 previous_status，不走 transitions
    STATUS_DEPRECATED: [STATUS_ARCHIVED],
    STATUS_ARCHIVED: [],  # 归档后不可修改
}


# ===== Schemas =====
class ComponentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str
    description: Optional[str] = None
    config_json: Dict[str, Any] = Field(default_factory=dict)
    folder_id: Optional[int] = None
    # 便捷字段：IDE 直接传 code + datasource_id，后端合并进 config_json
    code: Optional[str] = None
    datasource_id: Optional[int] = None


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None
    folder_id: Optional[int] = None
    code: Optional[str] = None
    datasource_id: Optional[int] = None


class RunSqlRequest(BaseModel):
    datasource_id: int
    sql: str


def _json_val(v):
    if v is None or isinstance(v, (int, float, bool, str)):
        return v
    return str(v)


def _serialize(c: Component) -> dict:
    status = c.status
    locked_by = getattr(c, 'locked_by', None)
    locked_at = getattr(c, 'locked_at', None)
    # 30分钟 TTL
    if locked_by and locked_at and datetime.utcnow() - locked_at > timedelta(minutes=30):
        locked_by = None
        locked_at = None
    return {
        "id": c.id,
        "name": c.name,
        "type": c.type,
        "description": c.description,
        "config_json": c.config_json or {},
        "version": c.version,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "status_color": STATUS_COLORS.get(status, "#86909C"),
        "ds_task_code": c.ds_task_code,
        "folder_id": c.folder_id if hasattr(c, 'folder_id') else None,
        "sort_order": c.sort_order if hasattr(c, 'sort_order') else 0,
        "code": (c.config_json or {}).get({'sql': 'sql', 'python': 'script', 'shell': 'script', 'datax': 'script'}.get(c.type, 'sql'), '') or '',
        "datasource_id": (c.config_json or {}).get('datasource_id'),
        "created_at": str(c.created_at) if c.created_at else None,
        "updated_at": str(c.updated_at) if c.updated_at else None,
        "locked_by": locked_by,
        "locked_at": str(locked_at) if locked_at else None,
    }


def _get_or_404(db: Session, comp_id: int) -> Component:
    c = db.query(Component).filter(Component.id == comp_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="组件不存在")
    return c
def _check_workflow_refs(db: Session, comp_id: int):
    """检查组件是否被工作流引用，若有则抛出 400"""
    from app.models.workflow import Workflow
    refs = db.query(Workflow.name).filter(
        Workflow.steps_json.contains(f'"component_id": {comp_id}'),
        Workflow.status.notin_(["offline", "archived"]),
    ).all()
    if refs:
        names = "、".join(r.name for r in refs[:5])
        raise HTTPException(
            status_code=400,
            detail=f"组件被以下工作流引用，请先下线相关工作流：{names}",
        )




def _run_sql(db: Session, datasource_id: int, sql: str):
    """复用的 SQL 执行逻辑，返回 dict"""
    from app.models.datasource import DataSource
    import sqlalchemy as sa

    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise HTTPException(404, "数据源不存在")

    from app.core.db_adapter import sqlalchemy_url
    url = sqlalchemy_url(ds)
    connect_args = {"connect_timeout": 10} if (ds.type or "").lower() in ("mysql", "postgresql") else {}
    engine = sa.create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    start = time.time()
    try:
        with engine.connect() as conn:
            res = conn.execute(sa.text(sql))
            duration_ms = int((time.time() - start) * 1000)
            if res.returns_rows:
                columns = list(res.keys())
                rows = [[_json_val(v) for v in row] for row in res.fetchmany(2000)]
                return {
                    "type": "table",
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "duration_ms": duration_ms,
                }
            else:
                conn.commit()
                return {
                    "type": "rowcount",
                    "affected": res.rowcount,
                    "duration_ms": duration_ms,
                }
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        engine.dispose()


# ===== CRUD =====
@router.get("")
def list_components(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    q = db.query(Component)
    if keyword:
        q = q.filter(Component.name.contains(keyword))
    if type:
        q = q.filter(Component.type == type)
    if status:
        q = q.filter(Component.status == status)
    total = q.count()
    items = q.order_by(Component.sort_order.asc(), Component.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_serialize(c) for c in items]}


@router.post("")
def create_component(
    req: ComponentCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    if req.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"非法组件类型,允许:{','.join(sorted(VALID_TYPES))}")
    cfg = dict(req.config_json or {})
    if req.code is not None:
        key = 'sql' if req.type == 'sql' else 'script'
        cfg[key] = req.code
    if req.datasource_id is not None:
        cfg['datasource_id'] = req.datasource_id
    c = Component(
        name=req.name,
        type=req.type,
        description=req.description,
        config_json=cfg,
        folder_id=req.folder_id,
        status=STATUS_DRAFT,
        version=1,
        created_by=current_user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize(c)


# ===== 文件夹 CRUD（必须在 /{comp_id} 之前定义，避免路由冲突）=====
from app.models.component_folder import ComponentFolder


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str
    parent_id: Optional[int] = None


class FolderRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


def _folder_depth(db: Session, parent_id: Optional[int]) -> int:
    depth = 0
    pid = parent_id
    while pid is not None and depth < 3:
        f = db.query(ComponentFolder).filter(ComponentFolder.id == pid).first()
        if not f:
            break
        pid = f.parent_id
        depth += 1
    return depth


@router.get("/folders")
def list_folders(
    folder_type: Optional[str] = Query(None, alias="type"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    q = db.query(ComponentFolder)
    if folder_type:
        q = q.filter(ComponentFolder.type == folder_type)
    items = q.order_by(ComponentFolder.sort_order.asc(), ComponentFolder.id.asc()).all()
    return [{"id": f.id, "name": f.name, "type": f.type, "parent_id": f.parent_id, "sort_order": f.sort_order} for f in items]


@router.post("/folders")
def create_folder(
    req: FolderCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    if req.parent_id is not None:
        parent = db.query(ComponentFolder).filter(ComponentFolder.id == req.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父文件夹不存在")
        depth = _folder_depth(db, req.parent_id)
        if depth >= 2:
            raise HTTPException(status_code=400, detail="最多支持 3 层嵌套")
    f = ComponentFolder(name=req.name, type=req.type, parent_id=req.parent_id)
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id, "name": f.name, "type": f.type, "parent_id": f.parent_id}


@router.put("/folders/{folder_id}")
def rename_folder(
    folder_id: int,
    req: FolderRename,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    f = db.query(ComponentFolder).filter(ComponentFolder.id == folder_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    f.name = req.name
    db.commit()
    return {"id": f.id, "name": f.name, "type": f.type, "parent_id": f.parent_id}


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    if db.query(ComponentFolder).filter(ComponentFolder.parent_id == folder_id).first():
        raise HTTPException(status_code=400, detail="请先删除子文件夹")
    if db.query(Component).filter(Component.folder_id == folder_id).first():
        raise HTTPException(status_code=400, detail="请先移走文件夹内的组件")
    f = db.query(ComponentFolder).filter(ComponentFolder.id == folder_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    db.delete(f)
    db.commit()
    return {"ok": True}


# ===== 临时 SQL 执行（无需保存为组件）=====
@router.post("/run-sql")
def run_sql_adhoc(
    req: RunSqlRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    """临时 SQL 执行，结果直接返回"""
    return _run_sql(db, req.datasource_id, req.sql)


@router.get("/{comp_id}")
def get_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    return _serialize(_get_or_404(db, comp_id))


@router.put("/{comp_id}")
def update_component(
    comp_id: int,
    req: ComponentUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    c = _get_or_404(db, comp_id)
    _check_lock(c, current_user)
    if c.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"组件当前状态「{c.status}」不允许编辑",
        )
    updates = req.model_dump(exclude_unset=True)
    old_name = c.name
    new_name = updates.get("name")
    # Handle convenience fields
    code = updates.pop('code', None)
    ds_id = updates.pop('datasource_id', None)
    if code is not None or ds_id is not None:
        cfg = dict(c.config_json or {})
        if code is not None:
            key = 'sql' if c.type == 'sql' else 'script'
            cfg[key] = code
        if ds_id is not None:
            cfg['datasource_id'] = ds_id
        updates['config_json'] = cfg
    for key, value in updates.items():
        setattr(c, key, value)
    if "config_json" in updates:
        c.status = STATUS_DRAFT
        c.version = (c.version or 1) + 1
    db.commit()
    db.refresh(c)

    # 改名时同步所有工作流 dag_json / steps_json 中的节点名称
    if new_name and new_name != old_name:
        _sync_component_name_in_workflows(db, comp_id, new_name)

    return _serialize(c)


def _sync_component_name_in_workflows(db: Session, comp_id: int, new_name: str):
    """把所有工作流中引用该组件的节点名称同步更新"""
    from app.models.workflow import Workflow
    import copy

    workflows = db.query(Workflow).all()
    for wf in workflows:
        changed = False
        # dag_json: {nodes: [{component_id, name, ...}, ...], edges: [...]}
        if wf.dag_json:
            dag = copy.deepcopy(wf.dag_json)
            for node in dag.get("nodes", []):
                if node.get("component_id") == comp_id:
                    node["name"] = new_name
                    changed = True
            if changed:
                wf.dag_json = dag
        # steps_json (legacy): [{component_id, name, ...}, ...]
        if wf.steps_json:
            steps = copy.deepcopy(wf.steps_json)
            for step in steps:
                if step.get("component_id") == comp_id:
                    step["name"] = new_name
                    changed = True
            if changed:
                wf.steps_json = steps
    if any(True for wf in workflows):
        db.commit()


@router.delete("/{comp_id}")
def delete_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    c = _get_or_404(db, comp_id)
    _check_lock(c, current_user)
    if c.status not in DELETABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"组件状态 {c.status},只有 draft/offline 状态允许删除;请先下线",
        )
    _check_workflow_refs(db, comp_id)
    db.delete(c)
    db.commit()
    return {"message": "删除成功"}


LOCK_TTL = timedelta(minutes=30)


def _check_lock(c: Component, current_user: SysUser):
    """检查锁：若被他人持有且未过期则拒绝"""
    if not c.locked_by:
        return
    if c.locked_by == current_user.id:
        return
    if c.locked_at and datetime.utcnow() - c.locked_at > LOCK_TTL:
        return  # 已过期
    raise HTTPException(status_code=409, detail=f"组件正在被其他用户编辑(user_id={c.locked_by})")


@router.post("/{comp_id}/lock")
def lock_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    """抢锁"""
    c = _get_or_404(db, comp_id)
    # 已被自己锁定 → 续期
    if c.locked_by == current_user.id:
        c.locked_at = datetime.utcnow()
        db.commit()
        return {"locked": True, "locked_by": current_user.id}
    # 被他人锁定且未过期
    if c.locked_by and c.locked_at and datetime.utcnow() - c.locked_at < LOCK_TTL:
        from app.models.user import SysUser as UserModel
        holder = db.query(UserModel).filter(UserModel.id == c.locked_by).first()
        holder_name = holder.username if holder else str(c.locked_by)
        raise HTTPException(status_code=409, detail=f"组件正在被 {holder_name} 编辑")
    # 抢锁
    c.locked_by = current_user.id
    c.locked_at = datetime.utcnow()
    db.commit()
    return {"locked": True, "locked_by": current_user.id}


@router.post("/{comp_id}/unlock")
def unlock_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """释放锁（持有者或管理员）"""
    c = _get_or_404(db, comp_id)
    if c.locked_by and c.locked_by != current_user.id:
        # 非持有者：仅管理员可强制解锁
        if not any(r.name == 'admin' for r in getattr(current_user, 'roles', [])):
            raise HTTPException(status_code=403, detail="只有锁持有者或管理员可解锁")
    c.locked_by = None
    c.locked_at = None
    db.commit()
    return {"locked": False}


# ===== 运行组件 =====
@router.post("/{comp_id}/run")
def run_component(
    comp_id: int,
    datasource_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    """运行组件：SQL 直连执行返回结果，Python/Shell 用 subprocess 执行返回日志"""
    c = _get_or_404(db, comp_id)
    cfg = c.config_json or {}
    code = (cfg.get("sql") or cfg.get("script") or cfg.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "组件代码为空")

    start = time.time()

    if c.type == "sql":
        ds_id = datasource_id or cfg.get("datasource_id")
        if not ds_id:
            raise HTTPException(400, "未指定数据源，请在 URL 加 ?datasource_id=X 或在组件中配置")
        return _run_sql(db, ds_id, code)

    elif c.type in ("python", "shell"):
        if c.type == "python":
            with tempfile.NamedTemporaryFile(
                suffix=".py", mode="w", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                tmp = f.name
            try:
                result = subprocess.run(
                    ["python3", tmp], capture_output=True, text=True, timeout=120
                )
            finally:
                os.unlink(tmp)
        else:
            result = subprocess.run(
                ["bash", "-c", code], capture_output=True, text=True, timeout=120
            )
        duration_ms = int((time.time() - start) * 1000)
        log = (result.stdout + result.stderr).strip() or "(无输出)"
        return {
            "type": "log",
            "ok": result.returncode == 0,
            "log": log,
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
        }

    else:
        raise HTTPException(400, f"不支持直接运行的组件类型: {c.type}")


# ===== 状态机操作 =====
@router.post("/{comp_id}/test")
def test_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:write")),
):
    c = _get_or_404(db, comp_id)
    if c.status not in {STATUS_DRAFT, STATUS_TESTED}:
        raise HTTPException(status_code=400, detail=f"状态 {c.status} 下不允许测试")
    c.status = STATUS_TESTED
    db.commit()
    db.refresh(c)
    return {"message": "测试通过", **_serialize(c)}


@router.post("/{comp_id}/publish")
def publish_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:publish")),
):
    c = _get_or_404(db, comp_id)
    if c.status != STATUS_TESTED:
        raise HTTPException(
            status_code=400,
            detail=f"只有 tested 状态可发布,当前状态 {c.status},请先测试",
        )
    c.status = STATUS_ONLINE
    db.commit()
    db.refresh(c)
    return {"message": "已发布", **_serialize(c)}


@router.post("/{comp_id}/quick-publish")
def quick_publish_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:publish")),
):
    """IDE 一键发布：draft/tested 均可直接上线，跳过 tested 前置要求"""
    c = _get_or_404(db, comp_id)
    if c.status == STATUS_ONLINE:
        return {"message": "已是发布状态", **_serialize(c)}
    if c.status == STATUS_OFFLINE:
        raise HTTPException(400, "已下线组件请先将状态改回 draft 再发布")
    c.status = STATUS_ONLINE
    db.commit()
    db.refresh(c)
    return {"message": "已发布", **_serialize(c)}


@router.post("/{comp_id}/offline")
def offline_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:publish")),
):
    c = _get_or_404(db, comp_id)
    if c.status != STATUS_ONLINE:
        raise HTTPException(status_code=400, detail=f"只有 online 状态可下线,当前 {c.status}")
    _check_workflow_refs(db, comp_id)
    c.status = STATUS_OFFLINE
    db.commit()
    db.refresh(c)
    return {"message": "已下线", **_serialize(c)}


# ===== 手动状态设置 =====

class SetStatusRequest(BaseModel):
    status: str


@router.put("/{comp_id}/status")
def set_component_status(
    comp_id: int,
    req: SetStatusRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """手动设置组件状态（仅允许 MANUAL_STATUSES 中的状态）"""
    c = _get_or_404(db, comp_id)
    new_status = req.status

    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"无效状态: {new_status}")

    if new_status in AUTO_STATUSES:
        raise HTTPException(status_code=400, detail=f"状态 {new_status} 为自动流转状态，不可手动设置")

    if c.status == STATUS_ARCHIVED:
        raise HTTPException(status_code=400, detail="已归档组件不可修改状态")

    # 处理暂停恢复（从 paused 转出去）
    if c.status == STATUS_PAUSED:
        # 恢复到 previous_status
        prev = getattr(c, 'previous_status', None) or STATUS_DEVELOPING
        c.status = prev
        try:
            c.previous_status = None
        except Exception:
            pass
        db.commit()
        db.refresh(c)
        return {"message": f"已恢复到 {STATUS_LABELS.get(prev, prev)}", **_serialize(c)}

    # 处理暂停：记录 previous_status
    if new_status == STATUS_PAUSED:
        try:
            c.previous_status = c.status
        except Exception:
            pass
        c.status = new_status
        db.commit()
        db.refresh(c)
        return {"message": "已暂停", **_serialize(c)}

    # 校验流转规则
    allowed = STATUS_TRANSITIONS.get(c.status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"状态流转非法: {STATUS_LABELS.get(c.status, c.status)} → {STATUS_LABELS.get(new_status, new_status)}"
        )

    c.status = new_status
    db.commit()
    db.refresh(c)
    return {"message": f"状态已更新为 {STATUS_LABELS.get(new_status, new_status)}", **_serialize(c)}


@router.post("/{comp_id}/resume")
def resume_component(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """从暂停状态恢复组件"""
    c = _get_or_404(db, comp_id)
    if c.status != STATUS_PAUSED:
        raise HTTPException(status_code=400, detail="组件未处于暂停状态")
    prev = getattr(c, 'previous_status', None) or STATUS_DEVELOPING
    c.status = prev
    try:
        c.previous_status = None
    except Exception:
        pass
    db.commit()
    db.refresh(c)
    return {"message": f"已恢复到 {STATUS_LABELS.get(prev, prev)}", **_serialize(c)}


# ===== 移动与排序 =====

class MoveComponentRequest(BaseModel):
    folder_id: Optional[int] = None
    sort_order: Optional[int] = None


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    orders: list[ReorderItem]


class MoveFolderRequest(BaseModel):
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


@router.put("/{comp_id}/move")
def move_component(
    comp_id: int,
    req: MoveComponentRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """移动组件到指定文件夹并/或更新排序"""
    c = _get_or_404(db, comp_id)
    if req.folder_id is not None:
        if req.folder_id != 0:
            f = db.query(ComponentFolder).filter(ComponentFolder.id == req.folder_id).first()
            if not f:
                raise HTTPException(status_code=404, detail="目标文件夹不存在")
        c.folder_id = req.folder_id if req.folder_id != 0 else None
    if req.sort_order is not None:
        c.sort_order = req.sort_order
    db.commit()
    db.refresh(c)
    return {"message": "移动成功", **_serialize(c)}


@router.post("/reorder")
def reorder_components(
    req: ReorderRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """批量更新组件排序"""
    for item in req.orders:
        c = db.query(Component).filter(Component.id == item.id).first()
        if c:
            c.sort_order = item.sort_order
    db.commit()
    return {"message": "排序已更新"}


@router.put("/folders/{folder_id}/move")
def move_folder(
    folder_id: int,
    req: MoveFolderRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """移动文件夹到指定父文件夹并/或更新排序"""
    f = db.query(ComponentFolder).filter(ComponentFolder.id == folder_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if req.parent_id is not None:
        if req.parent_id != 0:
            parent = db.query(ComponentFolder).filter(ComponentFolder.id == req.parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="目标父文件夹不存在")
            depth = _folder_depth(db, req.parent_id)
            if depth >= 2:
                raise HTTPException(status_code=400, detail="最多支持 3 层嵌套")
        f.parent_id = req.parent_id if req.parent_id != 0 else None
        # 重新计算 depth
        f.depth = _folder_depth(db, f.parent_id)
    if req.sort_order is not None:
        f.sort_order = req.sort_order
    db.commit()
    db.refresh(f)
    return {"id": f.id, "name": f.name, "type": f.type, "parent_id": f.parent_id, "depth": f.depth}
