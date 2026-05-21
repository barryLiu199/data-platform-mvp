import re
from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class HiveAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"hive://{self.ds.username}@{self.ds.host}:{self.ds.port}/{self._database}"

    def connect(self, db_override: Optional[str] = None):
        from impala.dbapi import connect
        return connect(
            host=self.ds.host, port=self.ds.port or 10000, user=self.ds.username,
            password=self.ds.password or "", database=db_override or self._database,
            auth_mechanism="PLAIN", timeout=5,
        )

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema=? AND table_name=?",
            (self._database, table),
        )

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SHOW DATABASES")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.connect(db_override=schema or self._database)
        try:
            cur = conn.cursor()
            cur.execute("SHOW TABLES")
            return [{"name": r[0], "comment": "", "type": "BASE TABLE", "rows": 0} for r in cur.fetchall()]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        if "." in table:
            schema, table = table.split(".", 1)
        conn = self.connect(db_override=schema or self._database)
        try:
            cur = conn.cursor()
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', table):
                raise ValueError(f"Invalid table name: {table}")
            cur.execute(f"DESCRIBE {table}")
            return [
                {"name": r[0], "type": r[1], "nullable": True, "comment": r[2] or ""}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
