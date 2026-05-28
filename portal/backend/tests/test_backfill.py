"""Backfill TDD tests — DS complement 引擎

测试覆盖：
- 创建端点：调 complement_data、验证参数、异常处理
- 列表/详情：分页、实例关联
- 停止：DS 侧终止 + 本地状态
- 重试：单实例重跑
- 状态同步：_poll_and_sync 逻辑
- reaper：重启后恢复同步
"""
import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.backfill import (
    router as backfill_router,
    _sync_backfill_status,
    _poll_and_sync,
    _map_ds_state,
    _parse_schedule_date,
    _rollup_counts,
    reap_stale_tasks,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.backfill import BackfillTask, BackfillInstance
from app.models.workflow import Workflow


@pytest.fixture
def app_client(db_session, clean_tables):
    """挂载 backfill 路由 + override get_db / get_current_user"""
    app = FastAPI()
    app.include_router(backfill_router, prefix="/api")

    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "tester"
    fake_user.role = "admin"

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield TestClient(app), db_session
    app.dependency_overrides.clear()


def _make_workflow(db, name="wf-A", ds_process_code=999):
    w = Workflow(name=name, status="online", steps_json=[], ds_process_code=ds_process_code)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ========== 创建端点 ==========

def test_create_calls_complement_and_starts_sync(app_client):
    client, db = app_client
    wf = _make_workflow(db)

    fake_ds = AsyncMock()
    fake_ds.complement_data.return_value = 12345  # DS command id

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds), \
         patch("app.api.backfill._schedule_sync") as mock_sync:
        resp = client.post("/api/backfill", json={
            "workflow_id": wf.id,
            "date_from": "2025-01-01",
            "date_to": "2025-01-05",
            "parallel": 2,
            "has_dep": 0,
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_count"] == 5
    assert data["status"] == "running"
    # complement_data 被调用，参数正确
    fake_ds.complement_data.assert_awaited_once()
    call_args = fake_ds.complement_data.call_args
    assert call_args[0][0] == 999  # pd_code
    assert "2025-01-01" in call_args[0][1]  # start_date
    assert "2025-01-05" in call_args[0][2]  # end_date
    assert call_args[1]["run_mode"] == "RUN_MODE_PARALLEL"  # has_dep=0
    # 状态同步已启动
    assert mock_sync.called

    # DB 中 task 记录
    t = db.query(BackfillTask).filter(BackfillTask.id == data["id"]).first()
    assert t.ds_command_type == "COMPLEMENT_DATA"
    assert t.ds_command_id == 12345


def test_create_serial_mode(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    fake_ds = AsyncMock()
    fake_ds.complement_data.return_value = 111

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds), \
         patch("app.api.backfill._schedule_sync"):
        resp = client.post("/api/backfill", json={
            "workflow_id": wf.id,
            "date_from": "2025-01-01",
            "date_to": "2025-01-03",
            "parallel": 1,
            "has_dep": 1,
        })
    assert resp.status_code == 200
    call_args = fake_ds.complement_data.call_args
    assert call_args[1]["run_mode"] == "RUN_MODE_SERIAL"


def test_create_rejects_inverted_date_range(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    resp = client.post("/api/backfill", json={
        "workflow_id": wf.id,
        "date_from": "2025-01-10",
        "date_to": "2025-01-01",
        "parallel": 1,
        "has_dep": 0,
    })
    assert resp.status_code == 400


def test_create_rejects_missing_workflow(app_client):
    client, db = app_client
    resp = client.post("/api/backfill", json={
        "workflow_id": 99999,
        "date_from": "2025-01-01",
        "date_to": "2025-01-02",
        "parallel": 1,
        "has_dep": 0,
    })
    assert resp.status_code == 404


def test_create_rejects_unpublished_workflow(app_client):
    client, db = app_client
    wf = _make_workflow(db, ds_process_code=None)
    resp = client.post("/api/backfill", json={
        "workflow_id": wf.id,
        "date_from": "2025-01-01",
        "date_to": "2025-01-02",
        "parallel": 1,
        "has_dep": 0,
    })
    assert resp.status_code == 400


def test_create_returns_502_when_ds_fails(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    fake_ds = AsyncMock()
    fake_ds.complement_data.return_value = None

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds):
        resp = client.post("/api/backfill", json={
            "workflow_id": wf.id,
            "date_from": "2025-01-01",
            "date_to": "2025-01-02",
            "parallel": 1,
            "has_dep": 0,
        })
    assert resp.status_code == 502


def test_create_clamps_parallel_to_valid_range(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    r1 = client.post("/api/backfill", json={
        "workflow_id": wf.id, "date_from": "2025-01-01",
        "date_to": "2025-01-02", "parallel": 0, "has_dep": 0,
    })
    r2 = client.post("/api/backfill", json={
        "workflow_id": wf.id, "date_from": "2025-01-01",
        "date_to": "2025-01-02", "parallel": 21, "has_dep": 0,
    })
    assert r1.status_code in (400, 422)
    assert r2.status_code in (400, 422)


# ========== 列表 / 详情 ==========

def test_list_backfill_returns_recent_first(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    fake_ds = AsyncMock()
    fake_ds.complement_data.return_value = 1

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds), \
         patch("app.api.backfill._schedule_sync"):
        for i in range(3):
            client.post("/api/backfill", json={
                "workflow_id": wf.id, "date_from": "2025-01-01",
                "date_to": "2025-01-02", "parallel": 1, "has_dep": 0,
            })
    resp = client.get("/api/backfill")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    ids = [it["id"] for it in items]
    assert ids == sorted(ids, reverse=True)


def test_get_backfill_includes_instances(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    # 手动创建 task + instances
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 3),
        parallel=1, has_dep=0, status="running", total_count=3,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.flush()
    for i in range(3):
        db.add(BackfillInstance(
            backfill_id=t.id, run_date=date(2025, 1, 1) + timedelta(days=i),
            seq=i + 1, status="pending",
        ))
    db.commit()

    resp = client.get(f"/api/backfill/{t.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == t.id
    assert len(data["instances"]) == 3


# ========== 停止 ==========

def test_stop_terminates_ds_instances(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 3),
        parallel=1, has_dep=0, status="running", total_count=3,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.flush()
    # 1 running with ds_instance_id, 2 pending
    db.add(BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 1), seq=1,
        status="running", ds_instance_id=100,
    ))
    db.add(BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 2), seq=2, status="pending",
    ))
    db.add(BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 3), seq=3, status="pending",
    ))
    db.commit()

    fake_ds = AsyncMock()
    fake_ds.stop_process_instance.return_value = True

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds):
        resp = client.post(f"/api/backfill/{t.id}/stop")
    assert resp.status_code == 200

    db.expire_all()
    t2 = db.query(BackfillTask).filter(BackfillTask.id == t.id).first()
    assert t2.status == "stopped"

    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == t.id
    ).order_by(BackfillInstance.seq).all()
    assert insts[0].status == "failed"  # running → failed (stopped)
    assert insts[1].status == "skipped"  # pending → skipped
    assert insts[2].status == "skipped"
    fake_ds.stop_process_instance.assert_awaited_once_with(100)


# ========== 重试 ==========

def test_retry_calls_start_process_instance(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 2),
        parallel=1, has_dep=0, status="failed", total_count=2,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.flush()
    inst = BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 1), seq=1,
        status="failed", error_msg="DS 实例状态: FAILURE",
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)

    fake_ds = AsyncMock()
    fake_ds.start_process_instance.return_value = {"id": 200}

    with patch("app.core.ds_client.get_ds_client", return_value=fake_ds), \
         patch("app.api.backfill._schedule_sync"):
        resp = client.post(f"/api/backfill/instances/{inst.id}/retry")
    assert resp.status_code == 200

    db.expire_all()
    fresh = db.query(BackfillInstance).filter(BackfillInstance.id == inst.id).first()
    assert fresh.status == "running"
    assert fresh.ds_instance_id == 200
    assert fresh.error_msg is None

    # task 回到 running
    t2 = db.query(BackfillTask).filter(BackfillTask.id == t.id).first()
    assert t2.status == "running"


def test_retry_rejects_non_failed_instance(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 1),
        parallel=1, has_dep=0, status="running", total_count=1,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.flush()
    inst = BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 1), seq=1, status="running",
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)

    resp = client.post(f"/api/backfill/instances/{inst.id}/retry")
    assert resp.status_code == 400


# ========== 状态映射工具函数 ==========

class TestMapDsState:
    def test_success(self):
        assert _map_ds_state("SUCCESS") == "success"

    def test_failure(self):
        assert _map_ds_state("FAILURE") == "failed"

    def test_kill(self):
        assert _map_ds_state("KILL") == "failed"

    def test_stop(self):
        assert _map_ds_state("STOP") == "failed"

    def test_running(self):
        assert _map_ds_state("RUNNING_EXECUTION") == "running"
        assert _map_ds_state("SUBMITTED_SUCCESS") == "running"

    def test_unknown(self):
        assert _map_ds_state("SOMETHING_ELSE") is None


class TestParseScheduleDate:
    def test_valid(self):
        assert _parse_schedule_date("2025-01-15 00:00:00") == date(2025, 1, 15)

    def test_empty(self):
        assert _parse_schedule_date("") is None
        assert _parse_schedule_date(None) is None

    def test_invalid(self):
        assert _parse_schedule_date("not-a-date") is None


# ========== 状态同步逻辑 ==========

def test_poll_and_sync_creates_and_updates_instances(db_session, clean_tables):
    db = db_session
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 3),
        parallel=1, has_dep=0, status="running", total_count=3,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # 模拟 DS 返回 3 个实例
    fake_ds = AsyncMock()
    fake_ds.query_process_instances.return_value = {
        "total": 3,
        "totalList": [
            {"id": 10, "state": "SUCCESS", "scheduleTime": "2025-01-01 00:00:00"},
            {"id": 11, "state": "RUNNING_EXECUTION", "scheduleTime": "2025-01-02 00:00:00"},
            {"id": 12, "state": "SUBMITTED_SUCCESS", "scheduleTime": "2025-01-03 00:00:00"},
        ],
    }

    changed = asyncio.run(_poll_and_sync(t, wf, fake_ds, db))
    assert changed is True

    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == t.id
    ).order_by(BackfillInstance.seq).all()
    assert len(insts) == 3
    assert insts[0].ds_instance_id == 10
    assert insts[0].status == "success"
    assert insts[1].ds_instance_id == 11
    assert insts[1].status == "running"
    assert insts[2].ds_instance_id == 12
    assert insts[2].status == "running"


def test_poll_and_sync_no_change_returns_false(db_session, clean_tables):
    db = db_session
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 1),
        parallel=1, has_dep=0, status="running", total_count=1,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.flush()
    inst = BackfillInstance(
        backfill_id=t.id, run_date=date(2025, 1, 1), seq=1,
        status="success", ds_instance_id=10,
    )
    db.add(inst)
    db.commit()
    db.refresh(t)

    fake_ds = AsyncMock()
    fake_ds.query_process_instances.return_value = {
        "total": 1,
        "totalList": [
            {"id": 10, "state": "SUCCESS", "scheduleTime": "2025-01-01 00:00:00"},
        ],
    }

    changed = asyncio.run(_poll_and_sync(t, wf, fake_ds, db))
    assert changed is False


# ========== rollup_counts ==========

def test_rollup_counts(db_session, clean_tables):
    db = db_session
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 3),
        parallel=1, has_dep=0, status="running", total_count=3,
    )
    db.add(t)
    db.flush()
    for i, status in enumerate(["success", "failed", "success"]):
        db.add(BackfillInstance(
            backfill_id=t.id, run_date=date(2025, 1, 1) + timedelta(days=i),
            seq=i + 1, status=status,
        ))
    db.commit()
    db.refresh(t)

    _rollup_counts(t, db)
    assert t.success_count == 2
    assert t.failed_count == 1


# ========== reaper ==========

def test_reap_stale_tasks_starts_sync_threads(db_session, clean_tables):
    db = db_session
    wf = _make_workflow(db)
    t = BackfillTask(
        workflow_id=wf.id, workflow_name=wf.name,
        date_from=date(2025, 1, 1), date_to=date(2025, 1, 2),
        parallel=1, has_dep=0, status="running", total_count=2,
        ds_command_type="COMPLEMENT_DATA",
    )
    db.add(t)
    db.commit()

    with patch("app.api.backfill.SessionLocal", return_value=db), \
         patch("app.api.backfill._sync_backfill_blocking") as mock_sync, \
         patch("threading.Thread") as mock_thread:
        mock_thread_inst = MagicMock()
        mock_thread.return_value = mock_thread_inst
        reap_stale_tasks()
        mock_thread.assert_called_once()
        mock_thread_inst.start.assert_called_once()
        # 确认传给 thread 的 target 是 _sync_backfill_blocking
        call_kwargs = mock_thread.call_args[1]
        assert call_kwargs["args"] == (t.id,)
