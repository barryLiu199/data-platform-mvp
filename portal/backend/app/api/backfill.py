"""Backfill (补数据/归历史) API

- POST /backfill           创建任务 + 展开实例 + 异步启动
- GET  /backfill           历史列表
- GET  /backfill/{id}      详情含全部实例
- POST /backfill/{id}/stop                  停止：pending → skipped
- POST /backfill/instances/{id}/retry       单实例重跑

执行引擎（_run_backfill）：
- has_dep=1：串行，遇 failed 停止后续并 skipped
- has_dep=0：asyncio.Semaphore(parallel) 控制并发
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Callable, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.models.backfill import BackfillTask, BackfillInstance
from app.models.workflow import Workflow
from app.models.user import SysUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backfill", tags=["补数据"])


# ===== Schemas =====
class CreateBackfillRequest(BaseModel):
    workflow_id: int
    date_from: date
    date_to: date
    parallel: int = Field(default=1, ge=1, le=20)
    has_dep: int = Field(default=0, ge=0, le=1)


def _serialize_task(t: BackfillTask) -> dict:
    return {
        "id": t.id,
        "workflow_id": t.workflow_id,
        "workflow_name": t.workflow_name,
        "date_from": t.date_from.isoformat() if t.date_from else None,
        "date_to": t.date_to.isoformat() if t.date_to else None,
        "parallel": t.parallel,
        "has_dep": t.has_dep,
        "status": t.status,
        "total_count": t.total_count,
        "success_count": t.success_count,
        "failed_count": t.failed_count,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


def _serialize_instance(i: BackfillInstance) -> dict:
    return {
        "id": i.id,
        "backfill_id": i.backfill_id,
        "run_date": i.run_date.isoformat() if i.run_date else None,
        "seq": i.seq,
        "status": i.status,
        "started_at": i.started_at.isoformat() if i.started_at else None,
        "finished_at": i.finished_at.isoformat() if i.finished_at else None,
        "error_msg": i.error_msg,
    }


# ===== 创建 =====
@router.post("")
def create_backfill(
    req: CreateBackfillRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    if req.date_from > req.date_to:
        raise HTTPException(400, "date_from 不能晚于 date_to")
    wf = db.query(Workflow).filter(Workflow.id == req.workflow_id).first()
    if not wf:
        raise HTTPException(404, "工作流不存在")

    days = (req.date_to - req.date_from).days + 1
    dates: List[date] = [req.date_from + timedelta(days=i) for i in range(days)]

    task = BackfillTask(
        workflow_id=wf.id,
        workflow_name=wf.name,
        date_from=req.date_from,
        date_to=req.date_to,
        parallel=req.parallel,
        has_dep=req.has_dep,
        status="pending",
        total_count=days,
        created_by=current_user.id,
    )
    db.add(task)
    db.flush()

    instances = [
        BackfillInstance(
            backfill_id=task.id,
            run_date=d,
            seq=idx + 1,
            status="pending",
        )
        for idx, d in enumerate(dates)
    ]
    db.add_all(instances)
    db.commit()
    db.refresh(task)

    _schedule_run(background_tasks, task.id)
    return _serialize_task(task)


def _schedule_run(background_tasks: BackgroundTasks, backfill_id: int) -> None:
    """单独包一层方便测试 patch"""
    background_tasks.add_task(_run_backfill_blocking, backfill_id)


def _run_backfill_blocking(backfill_id: int) -> None:
    """BackgroundTask 入口：同步包装异步执行"""
    try:
        asyncio.run(_run_backfill(backfill_id))
    except Exception:
        logger.exception("backfill %s 执行异常", backfill_id)


# ===== 列表 / 详情 =====
@router.get("")
def list_backfill(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    q = db.query(BackfillTask).order_by(BackfillTask.id.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_serialize_task(t) for t in items]}


@router.get("/{backfill_id}")
def get_backfill(
    backfill_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    t = db.query(BackfillTask).filter(BackfillTask.id == backfill_id).first()
    if not t:
        raise HTTPException(404, "补数据任务不存在")
    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == backfill_id
    ).order_by(BackfillInstance.seq).all()
    return {
        **_serialize_task(t),
        "instances": [_serialize_instance(i) for i in insts],
    }


# ===== 停止 / 重试 =====
@router.post("/{backfill_id}/stop")
def stop_backfill(
    backfill_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    t = db.query(BackfillTask).filter(BackfillTask.id == backfill_id).first()
    if not t:
        raise HTTPException(404, "补数据任务不存在")
    # 将所有 pending 改为 skipped；running 由执行循环自然结束
    db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == backfill_id,
        BackfillInstance.status == "pending",
    ).update({"status": "skipped"})
    t.status = "stopping"
    db.commit()
    return {"message": "已停止", "id": backfill_id}


@router.post("/instances/{inst_id}/retry")
def retry_instance(
    inst_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    inst = db.query(BackfillInstance).filter(BackfillInstance.id == inst_id).first()
    if not inst:
        raise HTTPException(404, "实例不存在")
    if inst.status not in ("failed", "skipped"):
        raise HTTPException(400, f"状态 {inst.status} 不支持重试")
    inst.status = "pending"
    inst.error_msg = None
    inst.started_at = None
    inst.finished_at = None
    db.commit()
    _schedule_run(background_tasks, inst.backfill_id)
    return {"message": "已重新加入队列", "id": inst_id}


# ===== 执行引擎 =====
async def _run_backfill(
    backfill_id: int,
    db_factory: Optional[Callable[[], Session]] = None,
) -> None:
    """异步执行整个 backfill 任务。

    Args:
        backfill_id: 任务 ID
        db_factory: 测试时可注入一个返回现有 Session 的工厂，避免 SQLAlchemy 跨连接
    """
    if db_factory is None:
        db_factory = SessionLocal
    db = db_factory()
    try:
        t = db.query(BackfillTask).filter(BackfillTask.id == backfill_id).first()
        if not t:
            return
        t.status = "running"
        db.commit()

        instances = db.query(BackfillInstance).filter(
            BackfillInstance.backfill_id == backfill_id,
            BackfillInstance.status == "pending",
        ).order_by(BackfillInstance.seq).all()

        if t.has_dep:
            # 串行：失败后剩余标 skipped
            failed = False
            for inst in instances:
                if failed:
                    inst.status = "skipped"
                    continue
                await _run_one(inst, db)
                db.commit()
                if inst.status == "failed":
                    failed = True
            db.commit()
        else:
            sem = asyncio.Semaphore(max(1, t.parallel))

            async def _guarded(inst):
                async with sem:
                    await _run_one(inst, db)

            await asyncio.gather(*[_guarded(i) for i in instances])
            db.commit()

        # 汇总进度
        all_insts = db.query(BackfillInstance).filter(
            BackfillInstance.backfill_id == backfill_id
        ).all()
        t.success_count = sum(1 for i in all_insts if i.status == "success")
        t.failed_count = sum(1 for i in all_insts if i.status == "failed")
        if t.failed_count > 0:
            t.status = "failed"
        elif all(i.status in ("success", "skipped") for i in all_insts):
            t.status = "succeeded"
        else:
            t.status = "stopped"
        t.finished_at = datetime.utcnow()
        db.commit()
    finally:
        if db_factory is SessionLocal:
            db.close()


async def _run_one(inst: BackfillInstance, db: Session) -> None:
    """运行单个实例 — 复用 workflow 内部 run 逻辑，传 run_date。

    生产实现：调 DS start_process_instance，传 startParams 包含 ${bizdate}=inst.run_date。
    单元测试会 patch 这个函数，所以这里只做最小可用实现。
    """
    from app.core.ds_client import get_ds_client
    from app.core.param_resolver import SYSTEM_PARAMS
    import json as _json

    inst.status = "running"
    inst.started_at = datetime.utcnow()
    db.commit()

    t = db.query(BackfillTask).filter(BackfillTask.id == inst.backfill_id).first()
    wf = db.query(Workflow).filter(Workflow.id == t.workflow_id).first()
    if not wf or not wf.ds_process_code:
        inst.status = "failed"
        inst.error_msg = "工作流未发布到 DS"
        inst.finished_at = datetime.utcnow()
        return

    try:
        ds = get_ds_client()
        params = {k: f(inst.run_date) for k, f in SYSTEM_PARAMS.items()}
        result = await ds.start_process_instance(
            wf.ds_process_code,
            start_params=_json.dumps(params, ensure_ascii=False),
        )
        if result is None:
            inst.status = "failed"
            inst.error_msg = (
                f"DS 触发失败：start-process-instance 返回 null（"
                f"pd_code={wf.ds_process_code} run_date={inst.run_date}）。"
                "通常原因：工作流未上线 / DS Master 过载 / 项目下没有 task。"
                "请到 DS 容器日志（dmp-ds）查看具体异常。"
            )
        else:
            inst.status = "success"
    except Exception as e:
        inst.status = "failed"
        inst.error_msg = f"{type(e).__name__}: {e}"
    finally:
        inst.finished_at = datetime.utcnow()
