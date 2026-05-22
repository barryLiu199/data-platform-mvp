from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class ClickHouseAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"clickhouse+native://{self.ds.username}:{self._password}@{self.ds.host}:{self.ds.port}/{self._database}"

    def connect(self, db_override: Optional[str] = None):
        from clickhouse_driver import Client
        from app.core.config import settings
        return Client(
            host=self.ds.host, port=self.ds.port or 9000,
            user=self.ds.username or "default", password=self.ds.password or "",
            database=db_override or self._database,
            settings={"max_execution_time": settings.SQL_QUERY_TIMEOUT_SEC},
        )

    def test_connection(self, table: Optional[str] = None) -> Tuple[bool, str]:
        try:
            conn = self.connect()
            try:
                conn.execute("SELECT 1")
                if table:
                    res = conn.execute(
                        "SELECT count() FROM system.tables WHERE database=%(db)s AND name=%(t)s",
                        {"db": self._database, "t": table},
                    )
                    if not res or res[0][0] == 0:
                        return False, f"表 {table} 不存在"
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {e}"

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            res = conn.execute("SHOW DATABASES")
            return [r[0] for r in res if r[0] not in ("system", "INFORMATION_SCHEMA", "information_schema")]
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        db = schema or self._database
        conn = self.connect(db_override=db)
        try:
            res = conn.execute(
                "SELECT name, comment, total_rows FROM system.tables WHERE database=%(db)s ORDER BY name",
                {"db": db},
            )
            return [{"name": r[0], "comment": r[1] or "", "type": "BASE TABLE", "rows": int(r[2] or 0)} for r in res]
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        if "." in table:
            schema, table = table.split(".", 1)
        db = schema or self._database
        conn = self.connect(db_override=db)
        try:
            res = conn.execute(
                "SELECT name, type, comment FROM system.columns "
                "WHERE database=%(db)s AND table=%(t)s ORDER BY position",
                {"db": db, "t": table},
            )
            return [
                {"name": r[0], "type": r[1], "nullable": "Nullable" in r[1], "comment": r[2] or ""}
                for r in res
            ]
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass
