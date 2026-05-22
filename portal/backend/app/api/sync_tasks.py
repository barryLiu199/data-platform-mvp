import logging
from datetime import datetime, timedelta
from typing import Optional, List, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.sync_task import SyncTask
from app.models.datasource import DataSource
from app.models.user import SysUser

router = APIRouter(prefix="/sync-tasks", tags=["同步任务"])


class FieldMapping(BaseModel):
    kind: Optional[str] = "column"   # column / constant / variable
    src: str
    dst: str
    type: Optional[str] = None


class SyncTaskCreate(BaseModel):
    name: str
    project_id: Optional[int] = None
    source_id: int
    target_id: int
    source_table: str
    target_table: str
    sync_type: str = "full"
    increment_column: Optional[str] = None
    field_mapping: Optional[List[FieldMapping]] = None
    where_clause: Optional[str] = None
    split_pk: Optional[str] = None
    write_mode: Optional[str] = "insert"
    channel: Optional[int] = 3
    pre_sql: Optional[List[str]] = None
    post_sql: Optional[List[str]] = None


def _serialize(task: SyncTask) -> dict:
    import json
    def _parse_json(s):
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return {
        "id": task.id,
        "name": task.name,
        "project_id": task.project_id,
        "source_id": task.source_id,
        "target_id": task.target_id,
        "source_table": task.source_table,
        "target_table": task.target_table,
        "sync_type": task.sync_type,
        "increment_column": task.increment_column,
        "field_mapping": _parse_json(task.field_mapping),
        "where_clause": task.where_clause,
        "split_pk": task.split_pk,
        "write_mode": task.write_mode or "insert",
        "channel": task.channel or 3,
        "pre_sql": _parse_json(task.pre_sql),
        "post_sql": _parse_json(task.post_sql),
        "ds_workflow_id": task.ds_workflow_id,
        "status": task.status,
        "last_run_time": str(task.last_run_time) if task.last_run_time else None,
        "last_run_status": task.last_run_status,
        "created_at": str(task.created_at) if task.created_at else None,
        "locked_by": getattr(task, 'locked_by', None),
        "locked_at": str(task.locked_at) if getattr(task, 'locked_at', None) else None,
    }


@router.get("")
def list_tasks(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[int] = Query(None, description="按项目过滤；传 0 表示未分组（project_id IS NULL）"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    query = db.query(SyncTask)
    if keyword:
        query = query.filter(SyncTask.name.contains(keyword))
    if status:
        query = query.filter(SyncTask.status == status)
    if project_id is not None:
        if project_id == 0:
            query = query.filter(SyncTask.project_id.is_(None))
        else:
            query = query.filter(SyncTask.project_id == project_id)
    total = query.count()
    items = query.order_by(SyncTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_serialize(t) for t in items]}


@router.post("")
def create_task(
    req: SyncTaskCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    import json
    source = db.query(DataSource).filter(DataSource.id == req.source_id).first()
    target = db.query(DataSource).filter(DataSource.id == req.target_id).first()
    if not source or not target:
        raise HTTPException(status_code=400, detail="数据源不存在")

    payload = req.model_dump()
    fm = payload.pop("field_mapping", None)
    if fm:
        payload["field_mapping"] = json.dumps(fm, ensure_ascii=False)
    if payload.get("pre_sql") is not None:
        payload["pre_sql"] = json.dumps(payload["pre_sql"], ensure_ascii=False)
    if payload.get("post_sql") is not None:
        payload["post_sql"] = json.dumps(payload["post_sql"], ensure_ascii=False)
    task = SyncTask(**payload, created_by=current_user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _serialize(task)


@router.get("/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _serialize(task)


LOCK_TTL = timedelta(minutes=30)


def _check_lock(task: SyncTask, current_user: SysUser):
    locked_by = getattr(task, 'locked_by', None)
    locked_at = getattr(task, 'locked_at', None)
    if not locked_by:
        return
    if locked_by == current_user.id:
        return
    if locked_at and datetime.utcnow() - locked_at > LOCK_TTL:
        return
    raise HTTPException(status_code=409, detail=f"任务正在被其他用户编辑(user_id={locked_by})")


@router.post("/{task_id}/lock")
def lock_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.locked_by == current_user.id:
        task.locked_at = datetime.utcnow()
        db.commit()
        return {"locked": True, "locked_by": current_user.id}
    if task.locked_by and task.locked_at and datetime.utcnow() - task.locked_at < LOCK_TTL:
        from app.models.user import SysUser as UserModel
        holder = db.query(UserModel).filter(UserModel.id == task.locked_by).first()
        holder_name = holder.username if holder else str(task.locked_by)
        raise HTTPException(status_code=409, detail=f"任务正在被 {holder_name} 编辑")
    task.locked_by = current_user.id
    task.locked_at = datetime.utcnow()
    db.commit()
    return {"locked": True, "locked_by": current_user.id}


@router.post("/{task_id}/unlock")
def unlock_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.locked_by and task.locked_by != current_user.id:
        if not any(r.name == 'admin' for r in getattr(current_user, 'roles', [])):
            raise HTTPException(status_code=403, detail="只有锁持有者或管理员可解锁")
    task.locked_by = None
    task.locked_at = None
    db.commit()
    return {"locked": False}


@router.put("/{task_id}")
def update_task(
    task_id: int,
    req: SyncTaskCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    import json
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _check_lock(task, current_user)
    data = req.model_dump(exclude_unset=True)
    if "field_mapping" in data:
        fm = data.pop("field_mapping")
        data["field_mapping"] = json.dumps(fm, ensure_ascii=False) if fm else None
    if "pre_sql" in data:
        v = data.pop("pre_sql")
        data["pre_sql"] = json.dumps(v, ensure_ascii=False) if v else None
    if "post_sql" in data:
        v = data.pop("post_sql")
        data["post_sql"] = json.dumps(v, ensure_ascii=False) if v else None
    for key, value in data.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return _serialize(task)


@router.patch("/{task_id}/status")
def set_task_status(
    task_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    """切换同步任务状态：active / draft / paused"""
    allowed = {"draft", "active", "paused"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的状态: {status}")
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.status = status
    db.commit()
    db.refresh(task)
    return _serialize(task)


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    from app.models.component import Component
    from app.models.workflow import Workflow

    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 清理关联的 datax Component（及其引用的 Workflow）
    comps = db.query(Component).filter(Component.type == "datax").all()
    for comp in comps:
        if (comp.config_json or {}).get("sync_task_id") == task_id:
            # 删除引用该组件的 Workflow
            wfs = db.query(Workflow).all()
            for wf in wfs:
                steps = wf.steps_json or []
                if any(s.get("component_id") == comp.id for s in steps):
                    db.delete(wf)
            db.delete(comp)

    db.delete(task)
    db.commit()
    return {"message": "删除成功"}


# ============ DataX 预览 & 连接测试 ============

class DataXPreviewRequest(BaseModel):
    source_id: int
    target_id: int
    source_table: str
    target_table: str
    sync_type: str = "full"
    increment_column: Optional[str] = None
    field_mapping: List[FieldMapping]
    where_clause: Optional[str] = None
    split_pk: Optional[str] = None
    write_mode: Optional[str] = "insert"
    pre_sql: Optional[List[str]] = None
    post_sql: Optional[List[str]] = None


class TestConnectionRequest(BaseModel):
    datasource_id: int
    table: Optional[str] = None


@router.get("/{task_id}/preview-datax")
def preview_datax(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """基于已保存的任务生成 DataX job.json（密码已打码）"""
    from app.core.datax_builder import build_for_sync_task
    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    src = db.query(DataSource).filter(DataSource.id == task.source_id).first()
    dst = db.query(DataSource).filter(DataSource.id == task.target_id).first()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="任务关联的数据源已被删除")
    try:
        job = build_for_sync_task(task, src, dst, mask_password=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"task_id": task_id, "datax": job}


@router.post("/preview")
def preview_unsaved(
    req: DataXPreviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """向导第 4 步：基于未落库的表单生成 DataX 预览"""
    from app.core.datax_builder import build_datax_job
    src = db.query(DataSource).filter(DataSource.id == req.source_id).first()
    dst = db.query(DataSource).filter(DataSource.id == req.target_id).first()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="数据源不存在")
    try:
        job = build_datax_job(
            source_ds=src,
            source_table=req.source_table,
            target_ds=dst,
            target_table=req.target_table,
            field_mapping=[m.model_dump() for m in req.field_mapping],
            sync_type=req.sync_type,
            increment_column=req.increment_column,
            where_clause=req.where_clause,
            split_pk=req.split_pk,
            write_mode=req.write_mode or "insert",
            pre_sql=req.pre_sql,
            post_sql=req.post_sql,
            mask_password=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"datax": job}


@router.post("/test-connection")
def test_connection(
    req: TestConnectionRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """测试数据源连接 & 表存在性"""
    ds = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    from app.core.db_adapter import test_connection as adapter_test
    ok, msg = adapter_test(ds, table=req.table)
    return {"ok": ok, "message": msg}


class RunSyncTaskRequest(BaseModel):
    run_date: Optional[str] = None  # YYYY-MM-DD；缺省 today()


@router.post("/{task_id}/run")
def run_sync_task(
    task_id: int,
    body: Optional[RunSyncTaskRequest] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    """手动运行同步任务：生成 DataX JSON 并执行"""
    import json
    import time
    import subprocess
    import tempfile
    from datetime import date as _date
    from app.core.param_resolver import resolve

    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    src = db.query(DataSource).filter(DataSource.id == task.source_id).first()
    dst = db.query(DataSource).filter(DataSource.id == task.target_id).first()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="任务关联的数据源已被删除")

    # 解析 run_date 并替换 where_clause 中的 ${bizdate} 等占位符
    rd = _date.today()
    if body and body.run_date:
        try:
            rd = _date.fromisoformat(body.run_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="run_date 必须为 YYYY-MM-DD")

    original_where = task.where_clause
    if original_where:
        task.where_clause = resolve(original_where, rd)

    from app.core.datax_builder import build_for_sync_task
    try:
        datax_job = build_for_sync_task(task, src, dst, mask_password=False)
    except ValueError as e:
        # 还原 where_clause，避免污染 ORM 对象
        task.where_clause = original_where
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # 还原 where_clause（仅用于 builder，不持久化）
        task.where_clause = original_where

    # 写入临时文件执行
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", delete=False, encoding="utf-8"
    ) as f:
        json.dump(datax_job, f, ensure_ascii=False)
        tmp_path = f.name

    start = time.time()
    try:
        result = subprocess.run(
            ["python", "/opt/datax/bin/datax.py", tmp_path],
            capture_output=True, text=True, timeout=600,
        )
        duration_ms = int((time.time() - start) * 1000)
        success = result.returncode == 0

        # 更新运行状态
        task.last_run_time = datetime.utcnow()
        task.last_run_status = "SUCCESS" if success else "FAILURE"
        db.commit()

        return {
            "success": success,
            "exit_code": result.returncode,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        task.last_run_time = datetime.utcnow()
        task.last_run_status = "FAILURE"
        db.commit()
        raise HTTPException(status_code=504, detail="DataX 执行超时(>600s)")
    finally:
        import os
        os.unlink(tmp_path)


@router.post("/{task_id}/publish-as-workflow")
async def publish_as_workflow(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("sync:write")),
):
    """将同步任务发布为单节点工作流：自动创建 datax 组件 + 单步工作流，并同步到 DS。"""
    import json
    from app.models.component import Component
    from app.models.workflow import Workflow
    from app.models.resource_access import SysResourceAccess

    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    source_ds = db.query(DataSource).filter(DataSource.id == task.source_id).first()
    target_ds = db.query(DataSource).filter(DataSource.id == task.target_id).first()
    if not source_ds or not target_ds:
        raise HTTPException(status_code=400, detail="任务关联的数据源已被删除")

    from app.core.datax_builder import build_for_sync_task
    try:
        datax_job = build_for_sync_task(task, source_ds, target_ds, mask_password=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_raw_json = json.dumps(datax_job, ensure_ascii=False)
    config = {
        "sync_task_id": task.id,
        "source_table": task.source_table,
        "target_table": task.target_table,
        "rawJson": new_raw_json,
    }

    # 幂等：若已存在关联的 datax 组件，只更新 config_json 和 rawJson，不重复创建
    existing_comp = (
        db.query(Component)
        .filter(Component.type == "datax")
        .all()
    )
    existing_comp = next(
        (c for c in existing_comp if (c.config_json or {}).get("sync_task_id") == task.id),
        None,
    )
    if existing_comp:
        existing_comp.config_json = config
        db.commit()
        db.refresh(existing_comp)
        wf_id = task.ds_workflow_id
        return {
            "component_id": existing_comp.id,
            "workflow_id": wf_id,
            "ds_process_code": None,
        }

    comp_name = f"[DataX] {task.name}"
    comp = Component(
        name=comp_name,
        type="datax",
        description=f"由同步任务 #{task.id} 自动生成",
        config_json=config,
        status="online",
        version=1,
        created_by=current_user.id,
    )
    db.add(comp)
    db.flush()

    db.add(SysResourceAccess(
        resource_type="component",
        resource_id=comp.id,
        subject_type="user",
        subject_id=current_user.id,
        permission="admin",
        granted_by=current_user.id,
    ))

    wf_name = f"[同步] {task.name}"
    wf = Workflow(
        name=wf_name,
        description=f"由同步任务 #{task.id} 自动生成的单节点工作流",
        tags=[],
        steps_json=[{"component_id": comp.id, "name": comp_name}],
        dag_json=None,
        cron_expression=None,
        schedule_status="OFFLINE",
        status="draft",
        version=1,
        priority=3,
        created_by=current_user.id,
    )
    db.add(wf)
    db.flush()

    db.add(SysResourceAccess(
        resource_type="workflow",
        resource_id=wf.id,
        subject_type="user",
        subject_id=current_user.id,
        permission="admin",
        granted_by=current_user.id,
    ))

    from app.api.workflow import _sync_to_ds
    pd_code = None
    try:
        pd_code, schedule_id = await _sync_to_ds(db, wf)
        wf.ds_process_code = pd_code
        wf.ds_schedule_id = schedule_id
        wf.status = "online"
        task.ds_workflow_id = wf.id
    except Exception as e:
        db.rollback()
        if pd_code:
            from app.core.ds_client import get_ds_client
            try:
                await get_ds_client().delete_process_definition(pd_code)
            except Exception as e:
                logger.warning("orphaned DS process %s: cleanup failed: %s", pd_code, e)
        raise HTTPException(status_code=502, detail=f"DS 同步失败：{e}")

    db.commit()
    return {
        "component_id": comp.id,
        "workflow_id": wf.id,
        "ds_process_code": wf.ds_process_code,
    }
