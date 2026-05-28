"""Backfill (补数据/归历史) API — DS complement 引擎

- POST /backfill           创建任务 → 调 DS complement API → 启动状态同步
- GET  /backfill           历史列表
- GET  /backfill/{id}      详情含全部实例
- POST /backfill/{id}/stop 停止：终止 DS 侧实例
- POST /backfill/instances/{id}/retry  单实例重跑

执行引擎：
- 一次 complement_data() 调用让 DS 自动按日展开实例
- portal 只做后台状态轮询同步
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Callable, List, Set

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

# DS 实例终态集合
_DS_FINAL_STATES: Set[str] = {
    "SUCCESS", "FAILURE", "STOP", "PAUSE", "KILL",
}
_DS_RUNNING_STATES: Set[str] = {
    "RUNNING_EXECUTION", "SUBMITTED_SUCCESS", "SERIAL_WAIT",
    "READY_PAUSE", "READY_STOP", "READY_BLOCK",
    "DELAY_EXECUTION", "DISPATCH", "WAIT_TASK_QUEUE",
}

SYNC_POLL_INTERVAL = 15  # seconds
SYNC_TIMEOUT = 3600  # 60 minutes


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
        "ds_instance_id": i.ds_instance_id,
    }


# ===== 创建 =====
@router.post("")
async def create_backfill(
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
    if not wf.ds_process_code:
        raise HTTPException(400, "工作流未发布到调度系统，请先发布")

    days = (req.date_to - req.date_from).days + 1
    run_mode = "RUN_MODE_SERIAL" if req.has_dep else "RUN_MODE_PARALLEL"

    # 调 DS complement API
    from app.core.ds_client import get_ds_client
    ds = get_ds_client()
    start_date = f"{req.date_from.isoformat()} 00:00:00"
    end_date = f"{req.date_to.isoformat()} 00:00:00"

    result = await ds.complement_data(
        wf.ds_process_code, start_date, end_date,
        run_mode=run_mode,
    )
    if result is None:
        raise HTTPException(502, "DS 补数据请求失败，请检查工作流是否已上线")

    task = BackfillTask(
        workflow_id=wf.id,
        workflow_name=wf.name,
        date_from=req.date_from,
        date_to=req.date_to,
        parallel=req.parallel,
        has_dep=req.has_dep,
        status="running",
        total_count=days,
        created_by=current_user.id,
        ds_command_type="COMPLEMENT_DATA",
        ds_command_id=result if isinstance(result, int) else None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    _schedule_sync(background_tasks, task.id)
    return _serialize_task(task)


def _schedule_sync(background_tasks: BackgroundTasks, backfill_id: int) -> None:
    """启动后台状态同步，单独包一层方便测试 patch"""
    background_tasks.add_task(_sync_backfill_blocking, backfill_id)


def _sync_backfill_blocking(backfill_id: int) -> None:
    """BackgroundTask 入口：同步包装异步轮询"""
    try:
        asyncio.run(_sync_backfill_status(backfill_id))
    except Exception:
        logger.exception("backfill %s 状态同步异常", backfill_id)


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
async def stop_backfill(
    backfill_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    t = db.query(BackfillTask).filter(BackfillTask.id == backfill_id).first()
    if not t:
        raise HTTPException(404, "补数据任务不存在")

    # 终止 DS 侧正在运行的实例
    from app.core.ds_client import get_ds_client
    ds = get_ds_client()
    running_insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == backfill_id,
        BackfillInstance.status == "running",
    ).all()
    for inst in running_insts:
        if inst.ds_instance_id:
            try:
                await ds.stop_process_instance(inst.ds_instance_id)
            except Exception as e:
                logger.warning("停止 DS 实例 %s 失败: %s", inst.ds_instance_id, e)
        inst.status = "failed"
        inst.error_msg = "用户手动停止"
        inst.finished_at = datetime.utcnow()

    # pending 的标 skipped
    db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == backfill_id,
        BackfillInstance.status == "pending",
    ).update({"status": "skipped"})

    t.status = "stopped"
    t.finished_at = datetime.utcnow()
    _rollup_counts(t, db)
    db.commit()
    return {"message": "已停止", "id": backfill_id}


@router.post("/instances/{inst_id}/retry")
async def retry_instance(
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

    t = db.query(BackfillTask).filter(BackfillTask.id == inst.backfill_id).first()
    if not t:
        raise HTTPException(404, "补数据任务不存在")
    wf = db.query(Workflow).filter(Workflow.id == t.workflow_id).first()
    if not wf or not wf.ds_process_code:
        raise HTTPException(400, "工作流未发布到调度系统")

    # 单实例重跑：调 start_process_instance + bizdate 参数
    from app.core.ds_client import get_ds_client
    from app.core.param_resolver import SYSTEM_PARAMS
    import json as _json

    ds = get_ds_client()
    params = {k: f(inst.run_date) for k, f in SYSTEM_PARAMS.items()}
    result = await ds.start_process_instance(
        wf.ds_process_code,
        start_params=_json.dumps(params, ensure_ascii=False),
    )
    if result is None:
        raise HTTPException(502, "DS 触发失败")

    inst.status = "running"
    inst.error_msg = None
    inst.started_at = datetime.utcnow()
    inst.finished_at = None
    inst.ds_instance_id = result.get("id") if isinstance(result, dict) else None

    # 任务回到 running
    if t.status in ("failed", "stopped", "succeeded", "timeout"):
        t.status = "running"
        t.finished_at = None
    db.commit()

    _schedule_sync(background_tasks, t.id)
    return {"message": "已重新提交", "id": inst_id}


# ===== 状态同步引擎 =====
async def _sync_backfill_status(
    backfill_id: int,
    db_factory: Optional[Callable[[], Session]] = None,
) -> None:
    """轮询 DS 实例状态，同步到本地表。只做读 DS → 写 portal DB，不做编排。"""
    from app.core.ds_client import get_ds_client

    if db_factory is None:
        db_factory = SessionLocal
    db = db_factory()
    try:
        t = db.query(BackfillTask).filter(BackfillTask.id == backfill_id).first()
        if not t or t.status not in ("running",):
            return
        wf = db.query(Workflow).filter(Workflow.id == t.workflow_id).first()
        if not wf or not wf.ds_process_code:
            return

        ds = get_ds_client()
        start_time = datetime.utcnow()
        last_change_time = datetime.utcnow()

        while True:
            # 检查超时
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > SYNC_TIMEOUT:
                t.status = "timeout"
                t.finished_at = datetime.utcnow()
                _rollup_counts(t, db)
                db.commit()
                logger.warning("backfill %s 同步超时 (%ds)", backfill_id, SYNC_TIMEOUT)
                return

            # 刷新 task 状态（可能被 stop 改了）
            db.refresh(t)
            if t.status in ("stopped", "failed"):
                return

            changed = await _poll_and_sync(t, wf, ds, db)
            if changed:
                last_change_time = datetime.utcnow()

            # 检查是否全部终态
            all_insts = db.query(BackfillInstance).filter(
                BackfillInstance.backfill_id == backfill_id
            ).all()
            if all_insts and all(
                i.status in ("success", "failed", "skipped") for i in all_insts
            ):
                _rollup_counts(t, db)
                if t.failed_count > 0:
                    t.status = "failed"
                else:
                    t.status = "succeeded"
                t.finished_at = datetime.utcnow()
                db.commit()
                return

            await asyncio.sleep(SYNC_POLL_INTERVAL)

    finally:
        if db_factory is SessionLocal:
            db.close()


async def _poll_and_sync(
    t: BackfillTask, wf: Workflow, ds, db: Session,
) -> bool:
    """一次轮询：查 DS 实例列表 → 同步到本地。返回是否有变化。"""
    data = await ds.query_process_instances(
        pd_code=wf.ds_process_code,
        page_no=1, page_size=100,
    )
    if not data or not data.get("totalList"):
        return False

    ds_instances = data["totalList"]
    changed = False

    # 获取本地已有的实例
    local_insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == t.id
    ).all()
    local_by_ds_id = {i.ds_instance_id: i for i in local_insts if i.ds_instance_id}
    local_by_date = {i.run_date: i for i in local_insts}

    for ds_inst in ds_instances:
        ds_id = ds_inst.get("id")
        ds_state = ds_inst.get("state", "")
        schedule_time_str = ds_inst.get("scheduleTime", "")

        # 解析 scheduleTime → date
        run_date = _parse_schedule_date(schedule_time_str)
        if not run_date:
            continue
        # 只关心日期范围内的实例
        if run_date < t.date_from or run_date > t.date_to:
            continue

        # 找到或创建本地实例
        local = local_by_ds_id.get(ds_id)
        if not local:
            local = local_by_date.get(run_date)
        if not local:
            # DS 展开的新实例，本地还没有
            seq = (run_date - t.date_from).days + 1
            local = BackfillInstance(
                backfill_id=t.id,
                run_date=run_date,
                seq=seq,
                status="pending",
            )
            db.add(local)
            db.flush()
            local_by_date[run_date] = local

        # 绑定 ds_instance_id
        if local.ds_instance_id != ds_id:
            local.ds_instance_id = ds_id
            changed = True

        # 状态映射
        new_status = _map_ds_state(ds_state)
        if new_status and local.status != new_status:
            old_status = local.status
            local.status = new_status
            if new_status == "running" and not local.started_at:
                local.started_at = datetime.utcnow()
            if new_status in ("success", "failed"):
                local.finished_at = datetime.utcnow()
                if new_status == "failed":
                    local.error_msg = f"DS 实例状态: {ds_state}"
            changed = True

    if changed:
        db.commit()
    return changed


def _map_ds_state(state: str) -> Optional[str]:
    """DS 实例状态 → 本地状态"""
    if state == "SUCCESS":
        return "success"
    if state in ("FAILURE", "KILL"):
        return "failed"
    if state in ("STOP", "PAUSE"):
        return "failed"
    if state in _DS_RUNNING_STATES:
        return "running"
    return None


def _parse_schedule_date(s: str) -> Optional[date]:
    """从 DS scheduleTime 字符串解析 date"""
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return None


def _rollup_counts(t: BackfillTask, db: Session) -> None:
    """汇总实例统计到 task"""
    all_insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == t.id
    ).all()
    t.success_count = sum(1 for i in all_insts if i.status == "success")
    t.failed_count = sum(1 for i in all_insts if i.status == "failed")
    t.total_count = max(t.total_count, len(all_insts))


# ===== 启动 reaper =====
def reap_stale_tasks() -> None:
    """启动时恢复 running 状态的 backfill 任务的状态同步。

    DS 侧可能还在跑，所以不标 failed，而是重新启动轮询。
    在 main.py startup 事件中调用。
    """
    db = SessionLocal()
    try:
        running = db.query(BackfillTask).filter(
            BackfillTask.status == "running"
        ).all()
        if not running:
            return
        logger.info("reaper: 发现 %d 个 running 状态的 backfill 任务，重新启动同步", len(running))
        for t in running:
            # 在后台线程中启动异步同步
            import threading
            thread = threading.Thread(
                target=_sync_backfill_blocking,
                args=(t.id,),
                daemon=True,
            )
            thread.start()
    finally:
        db.close()
