"""通用数据库适配器 — 兼容层

所有实际逻辑已迁移到 app/core/db_adapters/ 各适配器模块。
此文件保留原有函数签名作为向后兼容，内部委托到新的 adapter registry。

新代码应直接使用:
    from app.core.db_adapters import get_adapter
    adapter = get_adapter(datasource)
    tables = adapter.list_tables()
"""
from typing import List, Dict, Any, Optional, Tuple

from app.models.datasource import DataSource
from app.core.db_adapters import get_adapter


def sqlalchemy_url(ds: DataSource) -> str:
    return get_adapter(ds).sqlalchemy_url()


def _connect(ds: DataSource, db_override: Optional[str] = None):
    return get_adapter(ds).connect(db_override)


def test_connection(ds: DataSource, table: Optional[str] = None) -> Tuple[bool, str]:
    return get_adapter(ds).test_connection(table)


def list_databases(ds: DataSource) -> List[str]:
    return get_adapter(ds).list_databases()


def list_tables(ds: DataSource, schema: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_adapter(ds).list_tables(schema)


def list_columns(ds: DataSource, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_adapter(ds).list_columns(table, schema)
