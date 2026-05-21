"""Database Adapter Protocol and Registry.

Each supported database type implements BaseAdapter.
Register new databases by adding a module in this package and updating REGISTRY.

Usage:
    from app.core.db_adapters import get_adapter
    adapter = get_adapter(datasource)
    tables = adapter.list_tables()
"""
from typing import Protocol, List, Dict, Any, Optional, Tuple, runtime_checkable

from app.models.datasource import DataSource


@runtime_checkable
class BaseAdapter(Protocol):
    """Protocol that all database adapters must satisfy."""

    ds: DataSource

    def connect(self, db_override: Optional[str] = None) -> Any:
        """Return a native connection object. Caller is responsible for close()."""
        ...

    def sqlalchemy_url(self) -> str:
        """Generate SQLAlchemy connection URL."""
        ...

    def test_connection(self, table: Optional[str] = None) -> Tuple[bool, str]:
        """Test connectivity. Returns (ok, message)."""
        ...

    def list_databases(self) -> List[str]:
        """List all databases/schemas."""
        ...

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tables in schema. Returns [{name, comment, type, rows}]."""
        ...

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """List columns of a table. Returns [{name, type, nullable, comment}]."""
        ...


class AdapterBase:
    """Shared base with common patterns for SQL-based adapters."""

    def __init__(self, ds: DataSource):
        self.ds = ds

    @property
    def _database(self) -> str:
        return self.ds.database_name or ""

    @property
    def _password(self) -> str:
        return self.ds.password or ""

    def test_connection(self, table: Optional[str] = None) -> Tuple[bool, str]:
        """Default test: connect, SELECT 1, optionally check table exists."""
        try:
            conn = self.connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                if table:
                    sql, params = self._table_exists_query(table)
                    cur.execute(sql, params)
                    cnt = cur.fetchone()[0]
                    if cnt == 0:
                        return False, f"表 {table} 不存在"
                cur.close()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {e}"

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        """Override in subclass for dialect-specific table existence check."""
        raise NotImplementedError

    def _with_connection(self, db_override: Optional[str] = None):
        """Context-manager-like helper for subclasses."""
        conn = self.connect(db_override)
        return conn


# ─── Registry ────────────────────────────────────────────────────────────────

from app.core.db_adapters.mysql import MysqlAdapter
from app.core.db_adapters.postgresql import PostgresqlAdapter
from app.core.db_adapters.sqlserver import SqlServerAdapter
from app.core.db_adapters.oracle import OracleAdapter
from app.core.db_adapters.clickhouse import ClickHouseAdapter
from app.core.db_adapters.mongodb import MongoDBAdapter
from app.core.db_adapters.redis_adapter import RedisAdapter
from app.core.db_adapters.hive import HiveAdapter

REGISTRY: Dict[str, type] = {
    "mysql": MysqlAdapter,
    "postgresql": PostgresqlAdapter,
    "sqlserver": SqlServerAdapter,
    "oracle": OracleAdapter,
    "clickhouse": ClickHouseAdapter,
    "mongodb": MongoDBAdapter,
    "redis": RedisAdapter,
    "hive": HiveAdapter,
}


def get_adapter(ds: DataSource) -> AdapterBase:
    """Get the appropriate adapter for a datasource."""
    t = (ds.type or "").lower()
    cls = REGISTRY.get(t)
    if not cls:
        raise ValueError(f"不支持的数据源类型: {ds.type}")
    return cls(ds)
