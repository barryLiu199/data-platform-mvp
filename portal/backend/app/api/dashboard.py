import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ds_client import get_ds_client
from app.models.user import SysUser
from app.models.datasource import DataSource
from app.models.sync_task import SyncTask
from app.models.workflow import Workflow
from app.models.word_root import WordRoot

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])

# DS 状态 → 6 分类映射
_STATUS_BUCKETS = {
    "SUCCESS": "success",
    "SUBMITTED_SUCCESS": "submitted",
    "WAIT": "waiting",
    "DELAY": "waiting",
    "RUNNING_EXECUTION": "running",
    "FAILURE": "failure",
    "NEED_FAULT_TOLERANCE": "failure",
    "STOP": "stopped",
    "KILL": "stopped",
    "PAUSE": "stopped",
}

_CATEGORY_LABELS = {
    "success": "运行成功",
    "submitted": "提交成功",
    "waiting": "等待资源",
    "running": "运行中",
    "failure": "运行失败",
    "stopped": "强行停止",
}


@router.get("/schedule-overview")
async def get_schedule_overview(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    current_user: SysUser = Depends(get_current_user),
):
    """调度状态分布 — 支持自定义日期范围"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    if not start_date:
        start_date = yesterday.strftime("%Y-%m-%d")
    if not end_date:
        end_date = yesterday.strftime("%Y-%m-%d")

    ds = get_ds_client()
    pc = await ds._discover_project()

    # 初始化 6 分类
    buckets = {k: 0 for k in _CATEGORY_LABELS}
    total = 0

    if pc:
        state_data = await ds.get(
            "/projects/analysis/process-state-count",
            params={
                "startDate": f"{start_date} 00:00:00",
                "endDate": f"{end_date} 23:59:59",
            },
        )
        if state_data:
            for item in state_data.get("workflowInstanceStatusCounts", []):
                state = item.get("state", "")
                count = item.get("count", 0)
                bucket = _STATUS_BUCKETS.get(state)
                if bucket:
                    buckets[bucket] += count
                total += count

    categories = [
        {"name": _CATEGORY_LABELS[k], "key": k, "count": buckets[k]}
        for k in _CATEGORY_LABELS
    ]
    return {"categories": categories, "total": total}


@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    total_ds = db.query(func.count(DataSource.id)).scalar() or 0
    active_ds = db.query(func.count(DataSource.id)).filter(DataSource.status == 1).scalar() or 0
    total_tasks = db.query(func.count(SyncTask.id)).scalar() or 0
    active_tasks = db.query(func.count(SyncTask.id)).filter(SyncTask.status == "active").scalar() or 0

    # DS 统计
    ds = get_ds_client()
    pc = await ds._discover_project()

    workflow_total = 0
    yesterday_runs = yesterday_success = yesterday_failure = yesterday_pending = 0
    trend = []

    if pc:
        # 工作流总数
        defs = await ds.get(f"/projects/{pc}/process-definition", params={"pageNo": 1, "pageSize": 1})
        workflow_total = (defs or {}).get("total", 0)

        # 昨日统计
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        start = yesterday.strftime("%Y-%m-%d 00:00:00")
        end = yesterday.strftime("%Y-%m-%d 23:59:59")

        state_data = await ds.get("/projects/analysis/process-state-count",
                                  params={"startDate": start, "endDate": end})
        if state_data:
            counts = {s["state"]: s["count"] for s in state_data.get("workflowInstanceStatusCounts", [])}
            yesterday_success = counts.get("SUCCESS", 0)
            yesterday_failure = counts.get("FAILURE", 0)
            yesterday_pending = counts.get("RUNNING_EXECUTION", 0) + counts.get("SUBMITTED_SUCCESS", 0)
            yesterday_runs = sum(counts.values())

        # 近 7 天趋势 — 并行请求
        async def _fetch_day(i: int):
            d = today - timedelta(days=i)
            s = d.strftime("%Y-%m-%d 00:00:00")
            e = d.strftime("%Y-%m-%d 23:59:59")
            day_data = await ds.get("/projects/analysis/process-state-count",
                                    params={"startDate": s, "endDate": e})
            return (day_data or {}).get("totalCount", 0)

        results = await asyncio.gather(*[_fetch_day(i) for i in range(6, -1, -1)])
        trend = list(results)

    # 数据资产统计
    word_root_count = db.query(func.count(WordRoot.id)).scalar() or 0
    workflow_count = db.query(func.count(Workflow.id)).scalar() or 0

    return {
        "datasource_total": total_ds,
        "datasource_active": active_ds,
        "task_total": total_tasks,
        "task_active": active_tasks,
        "workflow_total": workflow_total or workflow_count,
        "yesterday_runs": yesterday_runs,
        "yesterday_success": yesterday_success,
        "yesterday_failure": yesterday_failure,
        "yesterday_pending": yesterday_pending,
        "workflow_trend": trend[-7:],
        "word_root_count": word_root_count,
    }
