"""DolphinScheduler API 代理路由 — 所有 /api/ds/* 端点"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ds_client import get_ds_client, DSClient
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.user import SysUser
from app.models.workflow import Workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ds", tags=["DolphinScheduler 代理"])


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _ds() -> DSClient:
    return get_ds_client()


async def _project_code(ds: DSClient) -> int:
    code = await ds._discover_project()
    if not code:
        raise HTTPException(503, "DS 项目不可用")
    return code


def _fmt_state(state: str) -> str:
    """DS 状态 → 简短标签"""
    mapping = {
        "SUCCESS": "SUCCESS",
        "FAILURE": "FAILURE",
        "RUNNING_EXECUTION": "RUNNING",
        "SUBMITTED_SUCCESS": "SUBMITTED",
        "READY_PAUSE": "PAUSE",
        "PAUSE": "PAUSE",
        "READY_STOP": "STOP",
        "STOP": "STOP",
        "DELAY_EXECUTION": "DELAY",
        "SERIAL_WAIT": "WAIT",
    }
    return mapping.get(state, state or "UNKNOWN")


# ─────────────────────────────────────────────
# Phase 1: 工作台统计
# ─────────────────────────────────────────────

@router.get("/stats")
async def dashboard_stats(current_user: SysUser = Depends(get_current_user)):
    """工作台调度统计数据"""
    ds = _ds()
    pc = await ds._discover_project()
    if not pc:
        return {"workflow_total": 0, "yesterday_runs": 0, "yesterday_success": 0,
                "yesterday_failure": 0, "yesterday_pending": 0, "workflow_trend": [0]*7}

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
    counts = {s["state"]: s["count"] for s in (state_data or {}).get("workflowInstanceStatusCounts", [])}
    success = counts.get("SUCCESS", 0)
    failure = counts.get("FAILURE", 0)
    running = counts.get("RUNNING_EXECUTION", 0)
    submitted = counts.get("SUBMITTED_SUCCESS", 0)
    pending = running + submitted
    total_runs = sum(counts.values())

    # 近 7 天趋势
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        s = d.strftime("%Y-%m-%d 00:00:00")
        e = d.strftime("%Y-%m-%d 23:59:59")
        day_data = await ds.get("/projects/analysis/process-state-count",
                                params={"startDate": s, "endDate": e})
        day_total = (day_data or {}).get("totalCount", 0)
        trend.append(day_total)

    return {
        "workflow_total": workflow_total,
        "yesterday_runs": total_runs,
        "yesterday_success": success,
        "yesterday_failure": failure,
        "yesterday_pending": pending,
        "workflow_trend": trend,
    }


# ─────────────────────────────────────────────
# Phase 2: 工作流管理
# ─────────────────────────────────────────────

@router.get("/workflows")
async def list_workflows(
    searchVal: str = "",
    pageNo: int = 1,
    pageSize: int = 20,
    current_user: SysUser = Depends(get_current_user),
):
    """工作流列表（合并调度状态 + 最近运行）"""
    ds = _ds()
    pc = await _project_code(ds)

    params = {"pageNo": pageNo, "pageSize": pageSize}
    if searchVal:
        params["searchVal"] = searchVal

    defs = await ds.get(f"/projects/{pc}/process-definition", params=params)
    if not defs:
        return {"list": [], "total": 0}

    # 获取调度信息
    schedules_raw = await ds.get(f"/projects/{pc}/schedules", params={"pageNo": 1, "pageSize": 200})
    schedule_map = {}
    for s in (schedules_raw or {}).get("totalList", []):
        pd_code = s.get("processDefinitionCode")
        if pd_code:
            schedule_map[pd_code] = s

    items = []
    for d in defs.get("totalList", []):
        code = d["code"]
        sch = schedule_map.get(code, {})

        # 获取最近一次运行
        inst = await ds.get(f"/projects/{pc}/process-instances", params={
            "pageNo": 1, "pageSize": 1,
            "processDefinitionCode": code,
        })
        last_items = (inst or {}).get("totalList") or []
        last_inst = last_items[0] if last_items else None

        items.append({
            "code": code,
            "name": d.get("name", ""),
            "description": d.get("description", ""),
            "releaseState": d.get("releaseState", "OFFLINE"),
            "scheduleStatus": "ONLINE" if sch else "OFFLINE",
            "scheduleId": sch.get("id"),
            "cronExpression": sch.get("crond", ""),
            "lastRunState": _fmt_state(last_inst["state"]) if last_inst else None,
            "lastRunTime": last_inst.get("startTime") if last_inst else None,
            "lastRunId": last_inst.get("id") if last_inst else None,
            "createTime": d.get("createTime"),
            "updateTime": d.get("updateTime"),
        })

    return {"list": items, "total": defs.get("total", 0)}


@router.post("/workflows/{code}/run")
async def run_workflow(code: int, current_user: SysUser = Depends(require_permission("workflow:write"))):
    """手动触发一次工作流执行"""
    ds = _ds()
    pc = await _project_code(ds)
    result = await ds.post(f"/projects/{pc}/executors/start-process-instance", data={
        "processDefinitionCode": code,
        "failureStrategy": "CONTINUE",
        "warningType": "NONE",
        "scheduleTime": "",
        "startParams": "",
    })
    if result is None:
        raise HTTPException(502, "触发工作流失败")
    return {"msg": "ok", "data": result}


@router.post("/workflows/{code}/online")
async def online_schedule(code: int, current_user: SysUser = Depends(require_permission("workflow:publish"))):
    """上线工作流调度"""
    ds = _ds()
    pc = await _project_code(ds)
    # 先查调度 ID
    schedules = await ds.get(f"/projects/{pc}/schedules", params={
        "pageNo": 1, "pageSize": 10,
        "processDefinitionCode": code,
    })
    sid = None
    for s in (schedules or {}).get("totalList", []):
        sid = s.get("id")
        break
    if not sid:
        raise HTTPException(404, "该工作流没有调度配置")
    result = await ds.post(f"/projects/{pc}/schedules/{sid}/online")
    if result is None:
        raise HTTPException(502, "上线调度失败")
    return {"msg": "ok"}


@router.post("/workflows/{code}/offline")
async def offline_schedule(code: int, current_user: SysUser = Depends(require_permission("workflow:publish"))):
    """下线工作流调度"""
    ds = _ds()
    pc = await _project_code(ds)
    schedules = await ds.get(f"/projects/{pc}/schedules", params={
        "pageNo": 1, "pageSize": 10,
        "processDefinitionCode": code,
    })
    sid = None
    for s in (schedules or {}).get("totalList", []):
        sid = s.get("id")
        break
    if not sid:
        raise HTTPException(404, "该工作流没有调度配置")
    result = await ds.post(f"/projects/{pc}/schedules/{sid}/offline")
    if result is None:
        raise HTTPException(502, "下线调度失败")
    return {"msg": "ok"}


@router.post("/workflows/{code}/rerun")
async def rerun_workflow(code: int, current_user: SysUser = Depends(require_permission("workflow:write"))):
    """重跑最近一次失败的工作流实例"""
    ds = _ds()
    pc = await _project_code(ds)
    # 找最近一次失败实例
    insts = await ds.get(f"/projects/{pc}/process-instances", params={
        "pageNo": 1, "pageSize": 1,
        "processDefinitionCode": code,
        "stateType": "FAILURE",
    })
    fail_list = (insts or {}).get("totalList", [])
    if not fail_list:
        raise HTTPException(404, "没有找到失败的实例")
    instance_id = fail_list[0]["id"]
    result = await ds.post(f"/projects/{pc}/executors/execute", data={
        "processInstanceId": instance_id,
        "executeType": "REPEAT_RUNNING",
        "failureStrategy": "CONTINUE",
        "warningType": "NONE",
    })
    if result is None:
        raise HTTPException(502, "重跑失败")
    return {"msg": "ok"}


@router.post("/workflows/{code}/complement")
async def complement_workflow(
    code: int,
    start_date: str,
    end_date: str,
    run_mode: str = "serial",
    start_params: str = "",
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    """[已废弃] 旧补数端点 — 改用 POST /api/backfill。

    DS 3.2.x 的 scheduleTime 期望 JSON 而非逗号分隔，此端点未适配会 502。
    保留为 410 是为了让历史前端缓存版本得到明确错误而非神秘 502。
    """
    raise HTTPException(
        410,
        "/api/ds/workflows/{code}/complement 已废弃，请使用 /api/backfill。"
        "对应入口：工作流页 → 更多 → 补数",
    )


# ─────────────────────────────────────────────
# Phase 2: 运行记录
# ─────────────────────────────────────────────

@router.get("/instances")
async def list_instances(
    pageNo: int = 1,
    pageSize: int = 20,
    stateType: str = "",
    startDate: str = "",
    endDate: str = "",
    processDefinitionCode: int = 0,
    keyword: str = "",
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    """运行记录列表（所有工作流的实例）"""
    ds = _ds()
    pc = await _project_code(ds)
    params = {"pageNo": pageNo, "pageSize": pageSize}
    if stateType:
        params["stateType"] = stateType
    if startDate:
        params["startDate"] = startDate
    if endDate:
        params["endDate"] = endDate
    if processDefinitionCode:
        params["processDefinitionCode"] = processDefinitionCode
    if keyword:
        params["searchVal"] = keyword

    data = await ds.get(f"/projects/{pc}/process-instances", params=params)
    if not data:
        return {"list": [], "total": 0}

    # 构建 ds_process_code → Portal 工作流名称 的映射
    all_wf = db.query(Workflow.ds_process_code, Workflow.name).filter(
        Workflow.ds_process_code.isnot(None)
    ).all()
    code_to_name = {wf.ds_process_code: wf.name for wf in all_wf}

    items = []
    for inst in data.get("totalList", []):
        start = inst.get("startTime")
        end = inst.get("endTime")
        duration = None
        if start and end:
            try:
                fmt = "%Y-%m-%d %H:%M:%S"
                duration = int((datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds())
            except Exception:
                pass

        pd_code = inst.get("processDefinitionCode")
        # 优先用 Portal 工作流名称，fallback 到 DS 名称，再 fallback 到 code
        name = (
            code_to_name.get(pd_code)
            or inst.get("processDefinitionName")
            or (f"工作流-{pd_code}" if pd_code else f"实例-{inst.get('id')}")
        )

        # 触发类型: SCHEDULER / COMPLEMENT_DATA / manual
        cmd_type = inst.get("commandType", "")
        if "COMPLEMENT" in cmd_type:
            trigger_type = "complement"
        elif "SCHEDULER" in cmd_type:
            trigger_type = "schedule"
        else:
            trigger_type = "manual"

        # 业务日期：优先 scheduleTime（DS 调度/补数会写入），fallback 解析 commandParam.startParams.run_date
        biz_date = inst.get("scheduleTime") or ""
        cmd_param_raw = inst.get("commandParam") or ""
        if not biz_date and cmd_param_raw:
            try:
                import json as _json
                cp = _json.loads(cmd_param_raw) if isinstance(cmd_param_raw, str) else cmd_param_raw
                sp = cp.get("StartParams") or cp.get("startParams") or {}
                biz_date = sp.get("run_date") or sp.get("bizdate") or ""
            except Exception:
                pass

        items.append({
            "id": inst.get("id"),
            "processDefinitionCode": pd_code,
            "name": name,
            "state": _fmt_state(inst.get("state")),
            "triggerType": trigger_type,
            "startTime": start,
            "endTime": end,
            "duration": duration,
            "runTimes": inst.get("runTimes"),
            "scheduleTime": inst.get("scheduleTime"),
            "bizDate": biz_date,
            "commandType": cmd_type,
            "executorName": inst.get("executorName") or "",
        })

    # keyword 也按 Portal 名称做 Python 侧过滤（DS searchVal 只搜 DS 名称）
    if keyword:
        kw_lower = keyword.lower()
        items = [i for i in items if kw_lower in i["name"].lower() or kw_lower in str(i["id"])]

    return {"list": items, "total": data.get("total", 0)}


@router.get("/instances/calendar")
async def instances_calendar(
    days: int = 30,
    current_user: SysUser = Depends(get_current_user),
):
    """近 N 天日历热力图数据"""
    ds = _ds()
    pc = await _project_code(ds)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        s = d.strftime("%Y-%m-%d 00:00:00")
        e = d.strftime("%Y-%m-%d 23:59:59")
        data = await ds.get("/projects/analysis/process-state-count",
                            params={"startDate": s, "endDate": e})
        counts = {x["state"]: x["count"] for x in (data or {}).get("workflowInstanceStatusCounts", [])}
        total = sum(counts.values())
        success = counts.get("SUCCESS", 0)
        failure = counts.get("FAILURE", 0)
        result.append({
            "date": d.strftime("%Y-%m-%d"),
            "total": total,
            "success": success,
            "failure": failure,
            "rate": round(success / total, 4) if total > 0 else None,
        })

    return result


@router.get("/instances/{instance_id}/tasks")
async def list_instance_tasks(
    instance_id: int,
    current_user: SysUser = Depends(get_current_user),
):
    """某次运行的所有任务"""
    ds = _ds()
    pc = await _project_code(ds)
    data = await ds.get(f"/projects/{pc}/task-instances", params={
        "processInstanceId": instance_id,
        "pageNo": 1, "pageSize": 100,
    })
    items = []
    for t in (data or {}).get("totalList", []):
        start = t.get("startTime")
        end = t.get("endTime")
        duration = None
        if start and end:
            try:
                fmt = "%Y-%m-%d %H:%M:%S"
                duration = int((datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds())
            except Exception:
                pass
        items.append({
            "id": t.get("id"),
            "name": t.get("name", ""),
            "taskType": t.get("taskType", ""),
            "state": _fmt_state(t.get("state")),
            "startTime": start,
            "endTime": end,
            "duration": duration,
        })
    return items


@router.get("/tasks/{task_id}/log")
async def get_task_log(
    task_id: int,
    current_user: SysUser = Depends(get_current_user),
):
    """获取任务日志"""
    ds = _ds()
    data = await ds.get("/log/detail", params={
        "taskInstanceId": task_id,
        "skipLineNum": 0,
        "limit": 10000,
    })
    if data is None:
        raise HTTPException(502, "获取日志失败")
    # data 通常是 {"message": "success", "msg": "..."} 或日志文本
    log_content = ""
    if isinstance(data, dict):
        log_content = data.get("msg", "") or data.get("message", "") or str(data)
    elif isinstance(data, str):
        log_content = data
    else:
        log_content = str(data)
    return {"taskInstanceId": task_id, "log": log_content}


@router.post("/instances/{instance_id}/rerun")
async def rerun_instance(
    instance_id: int,
    current_user: SysUser = Depends(require_permission("workflow:write")),
):
    """重跑指定实例"""
    ds = _ds()
    pc = await _project_code(ds)
    result = await ds.post(f"/projects/{pc}/executors/execute", data={
        "processInstanceId": instance_id,
        "executeType": "REPEAT_RUNNING",
        "failureStrategy": "CONTINUE",
        "warningType": "NONE",
    })
    if result is None:
        raise HTTPException(502, "重跑失败")
    return {"msg": "ok"}


# ─────────────────────────────────────────────
# Phase 4: 系统监控
# ─────────────────────────────────────────────

@router.get("/monitor")
async def ds_monitor(current_user: SysUser = Depends(get_current_user)):
    """DS 服务资源监控"""
    ds = _ds()
    healthy = await ds.healthy()

    # actuator/health 有 master/worker 状态
    try:
        resp = await ds._client.get(f"{ds._base_url}/actuator/health", timeout=5.0)
        health_data = resp.json().get("components", {})
    except Exception:
        health_data = {}

    # 通过 actuator/metrics 获取 JVM 信息
    jvm_info = {}
    try:
        mem_resp = await ds._client.get(
            f"{ds._base_url}/actuator/metrics/jvm.memory.max",
            cookies={"sessionId": ds._session_id} if ds._session_id else {},
            timeout=5.0,
        )
        if mem_resp.status_code == 200:
            mem_data = mem_resp.json()
            jvm_info["memoryMax"] = mem_data.get("measurements", [{}])[0].get("value", 0)

        used_resp = await ds._client.get(
            f"{ds._base_url}/actuator/metrics/jvm.memory.used",
            cookies={"sessionId": ds._session_id} if ds._session_id else {},
            timeout=5.0,
        )
        if used_resp.status_code == 200:
            used_data = used_resp.json()
            jvm_info["memoryUsed"] = used_data.get("measurements", [{}])[0].get("value", 0)

        cpu_resp = await ds._client.get(
            f"{ds._base_url}/actuator/metrics/process.cpu.usage",
            cookies={"sessionId": ds._session_id} if ds._session_id else {},
            timeout=5.0,
        )
        if cpu_resp.status_code == 200:
            cpu_data = cpu_resp.json()
            jvm_info["cpuUsage"] = cpu_data.get("measurements", [{}])[0].get("value", 0) * 100
    except Exception:
        pass

    max_mem = jvm_info.get("memoryMax", 0)
    used_mem = jvm_info.get("memoryUsed", 0)

    return {
        "healthy": healthy,
        "masterStatus": health_data.get("master", {}).get("status"),
        "workerStatus": health_data.get("worker", {}).get("status"),
        "dbStatus": health_data.get("db", {}).get("status"),
        "cpuUsage": round(jvm_info.get("cpuUsage", 0), 1),
        "memoryMax": max_mem,
        "memoryUsed": used_mem,
        "memoryUsage": round(used_mem / max_mem * 100, 1) if max_mem > 0 else 0,
    }


@router.get("/health")
async def ds_health():
    """DS 健康检查（无需认证，供内部调用）"""
    ds = _ds()
    healthy = await ds.healthy()
    return {"healthy": healthy}
