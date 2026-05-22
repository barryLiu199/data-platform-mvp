"""项目 (Project) — 平台级工作空间

用于同步任务和工作流分组。
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.project import Project
from app.models.sync_task import SyncTask
from app.models.workflow import Workflow
from app.models.user import SysUser

router = APIRouter(prefix="/projects", tags=["项目"])

# 系统调色板 — 8 色循环，按项目 id 分配，色弱友好
PALETTE = [
    "#2B5AED",  # 蓝
    "#00C9A7",  # 青
    "#722ED1",  # 紫
    "#FF7D00",  # 橙
    "#F53F3F",  # 红
    "#00B42A",  # 绿
    "#FFB400",  # 金
    "#14B8A6",  # 蓝绿
]


def _assign_color(project_id: int) -> str:
    """按 id 取模分配主题色"""
    return PALETTE[(project_id - 1) % len(PALETTE)]


def _serialize(p: Project, task_count: int = 0, workflow_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "code": p.code,
        "description": p.description,
        "color": p.color,
        "status": p.status,
        "is_default": bool(p.is_default),
        "owner_id": p.owner_id,
        "task_count": task_count,
        "workflow_count": workflow_count,
        "created_at": str(p.created_at) if p.created_at else None,
        "updated_at": str(p.updated_at) if p.updated_at else None,
    }


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    description: Optional[str] = None
    owner_id: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    status: Optional[int] = None
    owner_id: Optional[int] = None


@router.get("")
def list_projects(
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """列出所有项目（含每个项目的任务数）"""
    q = db.query(Project)
    if keyword:
        q = q.filter(Project.name.contains(keyword))
    projects = q.order_by(Project.is_default.desc(), Project.id.asc()).all()

    # 任务数聚合
    counts = dict(
        db.query(SyncTask.project_id, func.count(SyncTask.id))
        .group_by(SyncTask.project_id)
        .all()
    )
    # 未分组任务数 = project_id IS NULL
    unassigned = db.query(func.count(SyncTask.id)).filter(SyncTask.project_id.is_(None)).scalar() or 0

    # 工作流数聚合
    wf_counts = dict(
        db.query(Workflow.project_id, func.count(Workflow.id))
        .group_by(Workflow.project_id)
        .all()
    )
    wf_unassigned = db.query(func.count(Workflow.id)).filter(Workflow.project_id.is_(None)).scalar() or 0

    items = []
    for p in projects:
        cnt = counts.get(p.id, 0)
        wf_cnt = wf_counts.get(p.id, 0)
        if p.is_default:
            cnt = cnt + unassigned
            wf_cnt = wf_cnt + wf_unassigned
        items.append(_serialize(p, cnt, wf_cnt))
    return {"items": items, "total": len(items)}


@router.post("")
def create_project(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    # 唯一性
    if db.query(Project).filter(Project.name == req.name).first():
        raise HTTPException(status_code=400, detail=f"项目名「{req.name}」已存在")
    if db.query(Project).filter(Project.code == req.code).first():
        raise HTTPException(status_code=400, detail=f"项目编码「{req.code}」已存在")

    p = Project(
        name=req.name,
        code=req.code,
        description=req.description,
        owner_id=req.owner_id or current_user.id,
        created_by=current_user.id,
        color=PALETTE[0],  # 先放占位色，写库后按 id 重排
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    # 分配最终色
    p.color = _assign_color(p.id)
    db.commit()
    db.refresh(p)
    return _serialize(p, 0)


@router.get("/{project_id}")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    cnt = db.query(func.count(SyncTask.id)).filter(SyncTask.project_id == p.id).scalar() or 0
    wf_cnt = db.query(func.count(Workflow.id)).filter(Workflow.project_id == p.id).scalar() or 0
    if p.is_default:
        cnt += db.query(func.count(SyncTask.id)).filter(SyncTask.project_id.is_(None)).scalar() or 0
        wf_cnt += db.query(func.count(Workflow.id)).filter(Workflow.project_id.is_(None)).scalar() or 0
    return _serialize(p, cnt, wf_cnt)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    req: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if p.is_default and req.status == 0:
        raise HTTPException(status_code=400, detail="默认项目不可禁用")

    data = req.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != p.name:
        dup = db.query(Project).filter(Project.name == data["name"], Project.id != p.id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"项目名「{data['name']}」已存在")
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    cnt = db.query(func.count(SyncTask.id)).filter(SyncTask.project_id == p.id).scalar() or 0
    wf_cnt = db.query(func.count(Workflow.id)).filter(Workflow.project_id == p.id).scalar() or 0
    return _serialize(p, cnt, wf_cnt)


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    move_to: Optional[int] = Query(None, description="将原任务迁到的目标项目 id，不传则置 NULL（落入未分组）"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if p.is_default:
        raise HTTPException(status_code=400, detail="默认项目不可删除")

    # 把任务迁走
    target_pid = None
    if move_to is not None:
        target = db.query(Project).filter(Project.id == move_to).first()
        if not target:
            raise HTTPException(status_code=400, detail="目标项目不存在")
        target_pid = move_to

    db.query(SyncTask).filter(SyncTask.project_id == p.id).update(
        {SyncTask.project_id: target_pid}, synchronize_session=False
    )
    db.query(Workflow).filter(Workflow.project_id == p.id).update(
        {Workflow.project_id: target_pid}, synchronize_session=False
    )
    db.delete(p)
    db.commit()
    return {"message": "删除成功"}


def ensure_default_project(db: Session) -> Project:
    """启动时确保默认未分组项目存在"""
    p = db.query(Project).filter(Project.is_default == 1).first()
    if p:
        return p
    p = Project(
        name="未分组",
        code="default",
        description="系统默认项目，存放未指定归属的任务和工作流",
        color=PALETTE[0],
        status=1,
        is_default=1,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    p.color = _assign_color(p.id)
    db.commit()
    return p
