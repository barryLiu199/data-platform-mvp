from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class SqlServerAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"mssql+pymssql://{self.ds.username}:{self._password}@{self.ds.host}:{self.ds.port}/{self._database}"

    def connect(self, db_override: Optional[str] = None):
        import pymssql
        return pymssql.connect(
            server=self.ds.host, port=str(self.ds.port or 1433), user=self.ds.username,
            password=self.ds.password, database=db_override or self._database, login_timeout=5,
        )

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_CATALOG=%s AND TABLE_NAME=%s",
            (self._database, table),
        )

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sys.databases WHERE database_id > 4")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.connect(db_override=schema or self._database)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
            )
            return [{"name": r[0], "comment": "", "type": r[1] or "BASE TABLE", "rows": 0} for r in cur.fetchall()]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        if "." in table:
            schema, table = table.split(".", 1)
        conn = self.connect(db_override=schema or self._database)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                "FROM information_schema.COLUMNS WHERE TABLE_NAME=%s "
                "ORDER BY ORDINAL_POSITION", (table,),
            )
            return [
                {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "comment": ""}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
