"""Tests for app/core/migrations.py — 幂等性与迁移逻辑"""
import pytest
from unittest.mock import MagicMock, patch, call


# ---- run_all_migrations 调用所有子函数 ----

def test_run_all_migrations_calls_all():
    """确保 run_all_migrations() 调用全部迁移函数

    动态发现模块内所有 _migrate_* 函数并全部 mock：
    新增迁移函数时无需更新本测试，且漏 mock 会导致真实 SQL 在 sqlite 上执行而报错。
    """
    import inspect
    import app.core.migrations as m

    funcs = [
        name for name, obj in vars(m).items()
        if name.startswith("_migrate_") and inspect.isfunction(obj)
    ]
    assert funcs, "未发现任何 _migrate_* 迁移函数"

    mocks = {f: MagicMock() for f in funcs}
    with patch.multiple(m, **mocks):
        m.run_all_migrations()

    for f in funcs:
        mocks[f].assert_called_once()


# ---- 幂等性：列已存在时不执行 ALTER ----

def _mock_engine_with_existing_cols(cols: set):
    """返回 mock engine，information_schema 查询返回给定列集合"""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    # fetchall 返回列名行
    conn.execute.return_value.fetchall.return_value = [(c,) for c in cols]

    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


def test_migrate_component_columns_skips_when_exists():
    from app.core import migrations as m

    engine, conn = _mock_engine_with_existing_cols({"folder_id"})
    with patch.object(m, "engine", engine):
        m._migrate_component_columns()

    # execute 只被调用一次（SELECT），没有 ALTER
    assert conn.execute.call_count == 1


def test_migrate_component_columns_executes_alter_when_missing():
    from app.core import migrations as m

    engine, conn = _mock_engine_with_existing_cols(set())  # 列不存在
    with patch.object(m, "engine", engine):
        m._migrate_component_columns()

    # 应有 SELECT + ALTER
    assert conn.execute.call_count == 2
    # TextClause 对象，通过 .text 访问 SQL 字符串
    alter_sql = conn.execute.call_args_list[1].args[0].text
    assert "folder_id" in alter_sql


def test_migrate_sort_order_skips_when_exists():
    from app.core import migrations as m

    engine, conn = _mock_engine_with_existing_cols({"sort_order"})
    with patch.object(m, "engine", engine):
        m._migrate_component_sort_order()

    assert conn.execute.call_count == 1  # 只有 SELECT


def test_migrate_sync_task_adds_only_missing_cols():
    """sync_task 有 8 列要加，如果其中 3 列已存在，只 ALTER 5 次"""
    from app.core import migrations as m

    existing = {"project_id", "field_mapping", "where_clause"}  # 3 列已存在
    engine, conn = _mock_engine_with_existing_cols(existing)
    with patch.object(m, "engine", engine):
        m._migrate_sync_task_columns()

    # 1 次 SELECT + 5 次 ALTER
    assert conn.execute.call_count == 1 + 5


# ---- 表不存在时 CREATE TABLE ----

def _mock_engine_table_not_exists():
    """information_schema 查询返回空，表示表不存在"""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.fetchall.return_value = []
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


def _mock_engine_table_exists():
    """information_schema 查询返回非空，表示表已存在"""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.fetchall.return_value = [("alert_rule",)]
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


def test_migrate_alert_rule_creates_table_when_missing():
    from app.core import migrations as m

    engine, conn = _mock_engine_table_not_exists()
    with patch.object(m, "engine", engine):
        m._migrate_alert_rule_table()

    assert conn.execute.call_count == 2  # SELECT + CREATE
    create_sql = conn.execute.call_args_list[1].args[0].text
    assert "CREATE TABLE" in create_sql or "alert_rule" in create_sql


def test_migrate_alert_rule_skips_when_table_exists():
    from app.core import migrations as m

    engine, conn = _mock_engine_table_exists()
    with patch.object(m, "engine", engine):
        m._migrate_alert_rule_table()

    assert conn.execute.call_count == 1  # 只有 SELECT


def test_migrate_word_root_table_creates_when_missing():
    from app.core import migrations as m

    engine, conn = _mock_engine_table_not_exists()
    with patch.object(m, "engine", engine):
        m._migrate_word_root_table()

    assert conn.execute.call_count == 2
    create_sql = conn.execute.call_args_list[1].args[0].text
    assert "word_root" in create_sql


def test_migrate_notify_channel_table_creates_when_missing():
    from app.core import migrations as m

    engine, conn = _mock_engine_table_not_exists()
    with patch.object(m, "engine", engine):
        m._migrate_sys_notify_channel_table()

    assert conn.execute.call_count == 2
    create_sql = conn.execute.call_args_list[1].args[0].text
    assert "sys_notify_channel" in create_sql
