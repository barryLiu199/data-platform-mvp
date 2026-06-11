"""Tests for db_adapters 包 — SQLAlchemy URL 生成 + 表存在查询 + registry"""
import pytest
from unittest.mock import MagicMock

from app.core.db_adapter import sqlalchemy_url
from app.core.db_adapters import get_adapter


def _ds(type_: str, user: str = "u", pwd: str = "p", host: str = "h", port: int = 3306, db: str = "mydb"):
    ds = MagicMock()
    ds.type = type_
    ds.username = user
    ds.password = pwd
    ds.host = host
    ds.port = port
    ds.database_name = db
    return ds


# ---- sqlalchemy_url ----

def test_mysql_url():
    url = sqlalchemy_url(_ds("mysql"))
    assert url.startswith("mysql+pymysql://")
    assert "mydb" in url
    assert "charset=utf8mb4" in url


def test_postgresql_url():
    url = sqlalchemy_url(_ds("postgresql", port=5432))
    assert url.startswith("postgresql+psycopg2://")


def test_sqlserver_url():
    url = sqlalchemy_url(_ds("sqlserver", port=1433))
    assert url.startswith("mssql+pymssql://")


def test_oracle_url():
    url = sqlalchemy_url(_ds("oracle", port=1521))
    assert url.startswith("oracle+oracledb://")
    assert "service_name=mydb" in url


def test_clickhouse_url():
    url = sqlalchemy_url(_ds("clickhouse", port=9000))
    assert url.startswith("clickhouse+native://")


def test_hive_url():
    url = sqlalchemy_url(_ds("hive", port=10000))
    assert url.startswith("hive://")


def test_url_contains_credentials():
    url = sqlalchemy_url(_ds("mysql", user="admin", pwd="s3cr3t"))
    assert "admin" in url
    assert "s3cr3t" in url


def test_url_contains_host_and_port():
    url = sqlalchemy_url(_ds("mysql", host="db.internal", port=13306))
    assert "db.internal" in url
    assert "13306" in url


# ---- get_adapter registry ----

def test_get_adapter_returns_correct_type():
    from app.core.db_adapters.mysql import MysqlAdapter
    from app.core.db_adapters.hive import HiveAdapter
    assert isinstance(get_adapter(_ds("mysql")), MysqlAdapter)
    assert isinstance(get_adapter(_ds("hive")), HiveAdapter)


def test_get_adapter_case_insensitive():
    from app.core.db_adapters.mysql import MysqlAdapter
    assert isinstance(get_adapter(_ds("MySQL")), MysqlAdapter)


def test_get_adapter_unsupported_type_raises():
    with pytest.raises(ValueError, match="不支持"):
        get_adapter(_ds("foobar"))


# ---- _table_exists_query ----

def test_mysql_table_exists_query():
    sql, params = get_adapter(_ds("mysql"))._table_exists_query("orders")
    assert "information_schema" in sql.lower()
    assert params == ("mydb", "orders")


def test_postgresql_table_exists_query():
    sql, params = get_adapter(_ds("postgresql"))._table_exists_query("orders")
    assert "information_schema" in sql.lower()
    assert "orders" in params


def test_sqlserver_table_exists_query():
    sql, _params = get_adapter(_ds("sqlserver"))._table_exists_query("orders")
    assert "information_schema" in sql.lower()


def test_oracle_table_exists_query():
    sql, params = get_adapter(_ds("oracle"))._table_exists_query("orders")
    assert "all_tables" in sql.lower()
    assert params == ("MYDB", "ORDERS")  # oracle 转大写


def test_hive_table_exists_query():
    sql, _params = get_adapter(_ds("hive"))._table_exists_query("orders")
    assert "information_schema" in sql.lower()
