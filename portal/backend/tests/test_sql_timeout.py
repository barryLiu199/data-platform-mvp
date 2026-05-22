"""TDD tests for B3: SQL 查询超时保护

验证各 adapter 在 connect() 后设置了 session 级查询超时。
使用 sys.modules 注入 mock 驱动，避免依赖实际数据库驱动安装。
"""
import importlib
import os
import sys
import pytest
from unittest.mock import MagicMock, patch


# ---- 配置项 ----

def test_sql_query_timeout_default_is_30():
    """settings 默认 SQL_QUERY_TIMEOUT_SEC = 30"""
    import app.core.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.SQL_QUERY_TIMEOUT_SEC == 30


def test_sql_query_timeout_override_via_env():
    """通过 env 覆盖超时秒数"""
    import app.core.config as cfg
    os.environ["SQL_QUERY_TIMEOUT_SEC"] = "10"
    try:
        importlib.reload(cfg)
        assert cfg.settings.SQL_QUERY_TIMEOUT_SEC == 10
    finally:
        os.environ.pop("SQL_QUERY_TIMEOUT_SEC", None)
        importlib.reload(cfg)


# ---- Helper: 注入 mock 驱动模块 ----

def _inject_mock_module(name):
    """临时向 sys.modules 注入一个 MagicMock 作为驱动模块"""
    mock_mod = MagicMock()
    old = sys.modules.get(name)
    sys.modules[name] = mock_mod
    return mock_mod, old


def _restore_module(name, old):
    if old is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = old


# ---- MySQL ----

def test_mysql_sets_max_execution_time():
    """MysqlAdapter.connect() 应执行 SET SESSION max_execution_time=30000"""
    mock_pymysql, old = _inject_mock_module("pymysql")
    try:
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymysql.connect.return_value = mock_conn

        from app.core.db_adapters.mysql import MysqlAdapter
        ds = MagicMock()
        ds.host = "localhost"; ds.port = 3306; ds.username = "u"
        ds.password = "p"; ds.database_name = "testdb"

        adapter = MysqlAdapter(ds)
        adapter.connect()

        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        timeout_calls = [c for c in execute_calls if "max_execution_time" in c]
        assert len(timeout_calls) == 1, f"Expected 1 timeout SET, got {execute_calls}"
        assert "30000" in timeout_calls[0]
    finally:
        _restore_module("pymysql", old)


# ---- PostgreSQL ----

def test_postgresql_sets_statement_timeout():
    """PostgresqlAdapter.connect() 应执行 SET statement_timeout = '30s'"""
    mock_psycopg2, old = _inject_mock_module("psycopg2")
    try:
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        from app.core.db_adapters.postgresql import PostgresqlAdapter
        ds = MagicMock()
        ds.host = "localhost"; ds.port = 5432; ds.username = "u"
        ds.password = "p"; ds.database_name = "testdb"

        adapter = PostgresqlAdapter(ds)
        adapter.connect()

        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        timeout_calls = [c for c in execute_calls if "statement_timeout" in c]
        assert len(timeout_calls) == 1, f"Expected 1 timeout SET, got {execute_calls}"
        assert "30s" in timeout_calls[0]
    finally:
        _restore_module("psycopg2", old)


# ---- SQL Server ----

def test_sqlserver_sets_lock_timeout():
    """SqlServerAdapter.connect() 应执行 SET LOCK_TIMEOUT 30000"""
    mock_pymssql, old = _inject_mock_module("pymssql")
    try:
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymssql.connect.return_value = mock_conn

        from app.core.db_adapters.sqlserver import SqlServerAdapter
        ds = MagicMock()
        ds.host = "localhost"; ds.port = 1433; ds.username = "u"
        ds.password = "p"; ds.database_name = "testdb"

        adapter = SqlServerAdapter(ds)
        adapter.connect()

        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        timeout_calls = [c for c in execute_calls if "LOCK_TIMEOUT" in c]
        assert len(timeout_calls) == 1, f"Expected 1 timeout SET, got {execute_calls}"
        assert "30000" in timeout_calls[0]
    finally:
        _restore_module("pymssql", old)


# ---- ClickHouse ----

def test_clickhouse_sets_max_execution_time():
    """ClickHouseAdapter.connect() 应设置 settings={'max_execution_time': 30}"""
    mock_ch, old = _inject_mock_module("clickhouse_driver")
    try:
        from app.core.db_adapters.clickhouse import ClickHouseAdapter
        ds = MagicMock()
        ds.host = "localhost"; ds.port = 9000; ds.username = "default"
        ds.password = ""; ds.database_name = "testdb"

        adapter = ClickHouseAdapter(ds)
        adapter.connect()

        _, kwargs = mock_ch.Client.call_args
        assert kwargs.get("settings", {}).get("max_execution_time") == 30
    finally:
        _restore_module("clickhouse_driver", old)


# ---- 可配置性 ----

def test_mysql_timeout_respects_env():
    """SQL_QUERY_TIMEOUT_SEC=10 时 MySQL 应设 max_execution_time=10000"""
    import app.core.config as cfg
    os.environ["SQL_QUERY_TIMEOUT_SEC"] = "10"
    mock_pymysql, old = _inject_mock_module("pymysql")
    try:
        importlib.reload(cfg)

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymysql.connect.return_value = mock_conn

        from app.core.db_adapters.mysql import MysqlAdapter
        ds = MagicMock()
        ds.host = "localhost"; ds.port = 3306; ds.username = "u"
        ds.password = "p"; ds.database_name = "testdb"

        adapter = MysqlAdapter(ds)
        adapter.connect()

        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        timeout_calls = [c for c in execute_calls if "max_execution_time" in c]
        assert "10000" in timeout_calls[0]
    finally:
        os.environ.pop("SQL_QUERY_TIMEOUT_SEC", None)
        importlib.reload(cfg)
        _restore_module("pymysql", old)
