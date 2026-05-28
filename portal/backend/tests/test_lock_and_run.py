"""
TDD tests for:
  - component lock/unlock (app/api/component.py)
  - sync_task lock/unlock (app/api/sync_tasks.py)
  - _migrate_lock_columns idempotency (app/core/migrations.py)
  - POST /sync-tasks/{id}/run logic (app/api/sync_tasks.py)
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_user(uid=1, username="alice"):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.roles = []
    return u


def _make_component(locked_by=None, locked_at=None, status="draft"):
    c = MagicMock()
    c.id = 42
    c.locked_by = locked_by
    c.locked_at = locked_at
    c.status = status
    c.type = "sql"
    c.name = "test_comp"
    c.description = ""
    c.config_json = {}
    c.version = 1
    c.ds_task_code = None
    c.folder_id = None
    c.sort_order = 0
    c.created_at = None
    c.updated_at = None
    return c


def _make_sync_task(locked_by=None, locked_at=None):
    t = MagicMock()
    t.id = 7
    t.locked_by = locked_by
    t.locked_at = locked_at
    t.status = "draft"
    t.last_run_time = None
    t.last_run_status = None
    t.source_id = 1
    t.target_id = 2
    return t


def _make_db(obj):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = obj
    return db


# ─────────────────────────────────────────────
# _check_lock (component)
# ─────────────────────────────────────────────

class TestCheckLock:
    def test_no_lock_passes(self):
        from app.api.component import _check_lock
        c = _make_component(locked_by=None)
        user = _make_user(uid=1)
        _check_lock(c, user)  # should not raise

    def test_locked_by_self_passes(self):
        from app.api.component import _check_lock
        c = _make_component(locked_by=1, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        _check_lock(c, user)  # own lock → OK

    def test_locked_by_other_raises_409(self):
        from app.api.component import _check_lock
        c = _make_component(locked_by=99, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        with pytest.raises(HTTPException) as exc:
            _check_lock(c, user)
        assert exc.value.status_code == 409

    def test_expired_lock_passes(self):
        from app.api.component import _check_lock
        old = datetime.utcnow() - timedelta(minutes=31)
        c = _make_component(locked_by=99, locked_at=old)
        user = _make_user(uid=1)
        _check_lock(c, user)  # expired → OK


# ─────────────────────────────────────────────
# lock_component endpoint
# ─────────────────────────────────────────────

class TestLockComponent:
    def _call(self, comp, user):
        from app.api.component import lock_component
        db = _make_db(comp)
        return lock_component(comp_id=comp.id, db=db, current_user=user)

    def test_lock_free_component(self):
        comp = _make_component(locked_by=None)
        user = _make_user(uid=1)
        result = self._call(comp, user)
        assert result["locked"] is True
        assert comp.locked_by == 1
        assert comp.locked_at is not None

    def test_renew_own_lock(self):
        comp = _make_component(locked_by=1, locked_at=datetime.utcnow() - timedelta(minutes=5))
        user = _make_user(uid=1)
        old_at = comp.locked_at
        result = self._call(comp, user)
        assert result["locked"] is True
        assert comp.locked_at != old_at  # renewed

    def test_lock_held_by_other_raises_409(self):
        comp = _make_component(locked_by=99, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        # mock holder query
        from app.api import component as mod
        db = MagicMock()

        def query_side(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = comp
            return q

        db.query.side_effect = query_side

        with pytest.raises(HTTPException) as exc:
            mod.lock_component(comp_id=comp.id, db=db, current_user=user)
        assert exc.value.status_code == 409

    def test_expired_lock_can_be_stolen(self):
        old = datetime.utcnow() - timedelta(minutes=40)
        comp = _make_component(locked_by=99, locked_at=old)
        user = _make_user(uid=1)
        result = self._call(comp, user)
        assert result["locked"] is True
        assert comp.locked_by == 1


# ─────────────────────────────────────────────
# unlock_component endpoint
# ─────────────────────────────────────────────

class TestUnlockComponent:
    def _call(self, comp, user):
        from app.api.component import unlock_component
        db = _make_db(comp)
        return unlock_component(comp_id=comp.id, db=db, current_user=user)

    def test_owner_can_unlock(self):
        comp = _make_component(locked_by=1, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        result = self._call(comp, user)
        assert result["locked"] is False
        assert comp.locked_by is None
        assert comp.locked_at is None

    def test_non_owner_non_admin_raises_403(self):
        comp = _make_component(locked_by=99, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        with pytest.raises(HTTPException) as exc:
            self._call(comp, user)
        assert exc.value.status_code == 403

    def test_unlocked_component_ok(self):
        comp = _make_component(locked_by=None)
        user = _make_user(uid=1)
        result = self._call(comp, user)
        assert result["locked"] is False


# ─────────────────────────────────────────────
# sync_task _check_lock
# ─────────────────────────────────────────────

class TestSyncTaskCheckLock:
    def test_no_lock_passes(self):
        from app.api.sync_tasks import _check_lock
        task = _make_sync_task(locked_by=None)
        _check_lock(task, _make_user(uid=1))

    def test_locked_by_other_raises_409(self):
        from app.api.sync_tasks import _check_lock
        task = _make_sync_task(locked_by=99, locked_at=datetime.utcnow())
        with pytest.raises(HTTPException) as exc:
            _check_lock(task, _make_user(uid=1))
        assert exc.value.status_code == 409

    def test_expired_lock_passes(self):
        from app.api.sync_tasks import _check_lock
        old = datetime.utcnow() - timedelta(minutes=35)
        task = _make_sync_task(locked_by=99, locked_at=old)
        _check_lock(task, _make_user(uid=1))


# ─────────────────────────────────────────────
# lock_task endpoint
# ─────────────────────────────────────────────

class TestLockSyncTask:
    def _call(self, task, user):
        from app.api.sync_tasks import lock_task
        db = _make_db(task)
        return lock_task(task_id=task.id, db=db, current_user=user)

    def test_lock_free_task(self):
        task = _make_sync_task(locked_by=None)
        user = _make_user(uid=1)
        result = self._call(task, user)
        assert result["locked"] is True
        assert task.locked_by == 1

    def test_renew_own_lock(self):
        task = _make_sync_task(locked_by=1, locked_at=datetime.utcnow() - timedelta(minutes=5))
        user = _make_user(uid=1)
        result = self._call(task, user)
        assert result["locked"] is True

    def test_steal_expired_lock(self):
        old = datetime.utcnow() - timedelta(minutes=40)
        task = _make_sync_task(locked_by=99, locked_at=old)
        user = _make_user(uid=1)
        result = self._call(task, user)
        assert task.locked_by == 1


# ─────────────────────────────────────────────
# unlock_task endpoint
# ─────────────────────────────────────────────

class TestUnlockSyncTask:
    def _call(self, task, user):
        from app.api.sync_tasks import unlock_task
        db = _make_db(task)
        return unlock_task(task_id=task.id, db=db, current_user=user)

    def test_owner_can_unlock(self):
        task = _make_sync_task(locked_by=1, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        result = self._call(task, user)
        assert result["locked"] is False
        assert task.locked_by is None

    def test_non_owner_raises_403(self):
        task = _make_sync_task(locked_by=99, locked_at=datetime.utcnow())
        user = _make_user(uid=1)
        with pytest.raises(HTTPException) as exc:
            self._call(task, user)
        assert exc.value.status_code == 403


# ─────────────────────────────────────────────
# _migrate_lock_columns idempotency
# ─────────────────────────────────────────────

def _mock_engine_cols(existing_cols: set):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.fetchall.return_value = [(c,) for c in existing_cols]
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


class TestMigrateLockColumns:
    def test_adds_both_columns_when_missing(self):
        from app.core import migrations as m
        engine, conn = _mock_engine_cols(set())
        with patch.object(m, "engine", engine):
            m._migrate_lock_columns()
        # 2 tables × (1 SELECT + 2 ALTER) = 6 calls
        assert conn.execute.call_count == 6
        calls_sql = [c.args[0].text for c in conn.execute.call_args_list if hasattr(c.args[0], 'text')]
        assert any("locked_by" in s for s in calls_sql)
        assert any("locked_at" in s for s in calls_sql)

    def test_skips_existing_columns(self):
        from app.core import migrations as m
        # both columns already exist on both tables
        engine, conn = _mock_engine_cols({"locked_by", "locked_at"})
        with patch.object(m, "engine", engine):
            m._migrate_lock_columns()
        # 2 tables × 1 SELECT only = 2 calls
        assert conn.execute.call_count == 2

    def test_adds_only_missing_column(self):
        from app.core import migrations as m
        # locked_by exists, locked_at missing
        engine, conn = _mock_engine_cols({"locked_by"})
        with patch.object(m, "engine", engine):
            m._migrate_lock_columns()
        # 2 tables × (1 SELECT + 1 ALTER) = 4 calls
        assert conn.execute.call_count == 4


# ─────────────────────────────────────────────
# run_sync_task endpoint
# ─────────────────────────────────────────────

class TestRunSyncTask:
    """run_sync_task 已改为 async + DS 调度，测试需 await"""

    @pytest.mark.asyncio
    async def test_task_not_found_raises_404(self):
        from app.api.sync_tasks import run_sync_task
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run_sync_task(task_id=999, db=db, current_user=_make_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_workflow_auto_publishes(self):
        """没有关联工作流时，自动调 publish_as_workflow"""
        from app.api.sync_tasks import run_sync_task
        from app.models.sync_task import SyncTask

        task = _make_sync_task()
        task.ds_workflow_id = None
        db = MagicMock()

        def query_side(model):
            q = MagicMock()
            if model is SyncTask:
                q.filter.return_value.first.return_value = task
            else:
                q.filter.return_value.first.return_value = None
            return q
        db.query.side_effect = query_side

        with patch("app.api.sync_tasks.publish_as_workflow", new_callable=AsyncMock) as mock_pub:
            # publish_as_workflow 之后 task 仍然没有 ds_workflow_id → 502
            with pytest.raises(HTTPException) as exc:
                await run_sync_task(task_id=task.id, db=db, current_user=_make_user())
            assert exc.value.status_code == 502
            mock_pub.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_ds_submit(self):
        """已有 DS 工作流时，调 start_process_instance 并返回 success"""
        from app.api.sync_tasks import run_sync_task
        from app.models.sync_task import SyncTask
        from app.models.workflow import Workflow

        task = _make_sync_task()
        task.ds_workflow_id = 1

        wf = MagicMock(spec=Workflow)
        wf.ds_process_code = 12345

        db = MagicMock()

        def query_side(model):
            q = MagicMock()
            if model is SyncTask:
                q.filter.return_value.first.return_value = task
            elif model is Workflow:
                q.filter.return_value.first.return_value = wf
            else:
                q.filter.return_value.first.return_value = None
            return q
        db.query.side_effect = query_side

        fake_ds = AsyncMock()
        fake_ds.start_process_instance.return_value = {"id": 100}

        with patch("app.core.ds_client.get_ds_client", return_value=fake_ds), \
             patch("app.core.ds_client.DSClient.get_instance", return_value=fake_ds):
            result = await run_sync_task(task_id=task.id, db=db, current_user=_make_user())
        assert result["success"] is True
        assert "SUBMITTED" == task.last_run_status
