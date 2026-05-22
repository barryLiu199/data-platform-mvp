"""Backfill TDD tests — 模式 B: TestClient + SQLite + 直接调用执行引擎单测"""
import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.backfill import router as backfill_router, _run_backfill
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


def _make_workflow(db, name="wf-A"):
    w = Workflow(name=name, status="online", steps_json=[], ds_process_code=999)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------- 创建端点 ----------

def test_create_generates_correct_instance_count(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    # 屏蔽实际执行（BackgroundTasks 调度器）
    with patch("app.api.backfill._schedule_run") as p:
        resp = client.post(
            "/api/backfill",
            json={
                "workflow_id": wf.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-05",
                "parallel": 2,
                "has_dep": 0,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_count"] == 5
    instances = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == data["id"]
    ).all()
    assert len(instances) == 5
    assert p.called  # 调度器被触发


def test_instances_ordered_by_date(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        resp = client.post(
            "/api/backfill",
            json={
                "workflow_id": wf.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-03",
                "parallel": 1,
                "has_dep": 1,
            },
        )
    bid = resp.json()["id"]
    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == bid
    ).order_by(BackfillInstance.seq).all()
    assert [i.run_date for i in insts] == [
        date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3),
    ]
    assert [i.seq for i in insts] == [1, 2, 3]


def test_create_rejects_inverted_date_range(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    resp = client.post(
        "/api/backfill",
        json={
            "workflow_id": wf.id,
            "date_from": "2025-01-10",
            "date_to": "2025-01-01",
            "parallel": 1,
            "has_dep": 0,
        },
    )
    assert resp.status_code == 400


def test_create_rejects_missing_workflow(app_client):
    client, db = app_client
    resp = client.post(
        "/api/backfill",
        json={
            "workflow_id": 99999,
            "date_from": "2025-01-01",
            "date_to": "2025-01-02",
            "parallel": 1,
            "has_dep": 0,
        },
    )
    assert resp.status_code == 404


def test_create_clamps_parallel_to_valid_range(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    # parallel = 0 / 21 都应被拒
    r1 = client.post("/api/backfill", json={
        "workflow_id": wf.id, "date_from": "2025-01-01",
        "date_to": "2025-01-02", "parallel": 0, "has_dep": 0,
    })
    r2 = client.post("/api/backfill", json={
        "workflow_id": wf.id, "date_from": "2025-01-01",
        "date_to": "2025-01-02", "parallel": 21, "has_dep": 0,
    })
    assert r1.status_code == 400 or r1.status_code == 422
    assert r2.status_code == 400 or r2.status_code == 422


# ---------- 列表 / 详情 ----------

def test_list_backfill_returns_recent_first(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        for i in range(3):
            client.post("/api/backfill", json={
                "workflow_id": wf.id, "date_from": "2025-01-01",
                "date_to": "2025-01-02", "parallel": 1, "has_dep": 0,
            })
    resp = client.get("/api/backfill")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    # 最新的 id 排第一
    ids = [it["id"] for it in items]
    assert ids == sorted(ids, reverse=True)


def test_get_backfill_includes_instances(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id, "date_from": "2025-01-01",
            "date_to": "2025-01-03", "parallel": 1, "has_dep": 0,
        }).json()["id"]
    resp = client.get(f"/api/backfill/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == bid
    assert len(data["instances"]) == 3


# ---------- 停止 / 重试 ----------

def test_stop_marks_pending_as_skipped(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id, "date_from": "2025-01-01",
            "date_to": "2025-01-04", "parallel": 1, "has_dep": 0,
        }).json()["id"]
    # 模拟 1 个 success / 1 个 running / 2 个 pending
    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == bid
    ).order_by(BackfillInstance.seq).all()
    insts[0].status = "success"
    insts[1].status = "running"
    db.commit()

    resp = client.post(f"/api/backfill/{bid}/stop")
    assert resp.status_code == 200
    db.expire_all()
    insts2 = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == bid
    ).order_by(BackfillInstance.seq).all()
    statuses = [i.status for i in insts2]
    assert statuses[0] == "success"   # 已完成不变
    assert statuses[1] == "running"   # running 不强终止
    assert statuses[2] == "skipped"   # pending → skipped
    assert statuses[3] == "skipped"


def test_retry_resets_failed_to_pending(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id, "date_from": "2025-01-01",
            "date_to": "2025-01-02", "parallel": 1, "has_dep": 0,
        }).json()["id"]
    inst = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == bid
    ).first()
    inst.status = "failed"
    inst.error_msg = "boom"
    db.commit()

    with patch("app.api.backfill._schedule_run") as p:
        resp = client.post(f"/api/backfill/instances/{inst.id}/retry")
    assert resp.status_code == 200
    db.expire_all()
    fresh = db.query(BackfillInstance).filter(BackfillInstance.id == inst.id).first()
    assert fresh.status == "pending"
    assert fresh.error_msg is None
    assert p.called


# ---------- 执行引擎（asyncio） ----------

@pytest.mark.parametrize("parallel,total,expect_max_concurrent", [
    (1, 5, 1),
    (2, 5, 2),
    (3, 6, 3),
])
def test_parallel_semaphore_respected(app_client, parallel, total, expect_max_concurrent):
    """asyncio.Semaphore 应限制最大并发数"""
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id,
            "date_from": "2025-01-01",
            "date_to": (date(2025, 1, 1) + timedelta(days=total - 1)).isoformat(),
            "parallel": parallel, "has_dep": 0,
        }).json()["id"]

    concurrent = 0
    peak = 0

    async def fake_run_one(inst, db_):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0.01)
        concurrent -= 1
        inst.status = "success"

    with patch("app.api.backfill._run_one", new=fake_run_one):
        asyncio.run(_run_backfill(bid, db_factory=lambda: db))

    assert peak == expect_max_concurrent


def test_serial_stops_after_failure(app_client):
    """has_dep=1 时，第一个失败后后续应被 skipped"""
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id, "date_from": "2025-01-01",
            "date_to": "2025-01-04", "parallel": 1, "has_dep": 1,
        }).json()["id"]

    call_count = {"n": 0}

    async def fake_run_one(inst, db_):
        call_count["n"] += 1
        if call_count["n"] == 2:
            inst.status = "failed"
            inst.error_msg = "day-2 fail"
        else:
            inst.status = "success"

    with patch("app.api.backfill._run_one", new=fake_run_one):
        asyncio.run(_run_backfill(bid, db_factory=lambda: db))

    insts = db.query(BackfillInstance).filter(
        BackfillInstance.backfill_id == bid
    ).order_by(BackfillInstance.seq).all()
    statuses = [i.status for i in insts]
    # 第 1 天 success，第 2 天 failed，第 3/4 天 skipped
    assert statuses[0] == "success"
    assert statuses[1] == "failed"
    assert statuses[2] == "skipped"
    assert statuses[3] == "skipped"
    assert call_count["n"] == 2  # 只调了 2 次，没继续


def test_progress_counts_update_correctly(app_client):
    client, db = app_client
    wf = _make_workflow(db)
    with patch("app.api.backfill._schedule_run"):
        bid = client.post("/api/backfill", json={
            "workflow_id": wf.id, "date_from": "2025-01-01",
            "date_to": "2025-01-03", "parallel": 3, "has_dep": 0,
        }).json()["id"]

    async def fake_run_one(inst, db_):
        if inst.seq == 2:
            inst.status = "failed"
            inst.error_msg = "x"
        else:
            inst.status = "success"

    with patch("app.api.backfill._run_one", new=fake_run_one):
        asyncio.run(_run_backfill(bid, db_factory=lambda: db))

    db.expire_all()
    t = db.query(BackfillTask).filter(BackfillTask.id == bid).first()
    assert t.success_count == 2
    assert t.failed_count == 1
    assert t.status in ("failed", "succeeded")  # 有失败的应标 failed
    assert t.status == "failed"
