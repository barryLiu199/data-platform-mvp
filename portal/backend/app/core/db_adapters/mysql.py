from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class MysqlAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"mysql+pymysql://{self.ds.username}:{self._password}@{self.ds.host}:{self.ds.port}/{self._database}?charset=utf8mb4"

    def connect(self, db_override: Optional[str] = None):
        import pymysql
        return pymysql.connect(
            host=self.ds.host, port=self.ds.port or 3306, user=self.ds.username,
            password=self.ds.password, database=db_override or self._database,
            connect_timeout=5, charset="utf8mb4",
        )

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (self._database, table),
        )

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SHOW DATABASES")
            return [r[0] for r in cur.fetchall() if r[0] not in ("information_schema", "mysql", "performance_schema", "sys")]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        db = schema or self._database
        conn = self.connect(db_override=db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_TYPE, COALESCE(TABLE_ROWS, 0) "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME", (db,),
            )
            return [{"name": r[0], "comment": r[1] or "", "type": r[2] or "BASE TABLE", "rows": int(r[3] or 0)} for r in cur.fetchall()]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        if "." in table:
            schema, table = table.split(".", 1)
        db = schema or self._database
        conn = self.connect(db_override=db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "ORDER BY ORDINAL_POSITION", (db, table),
            )
            return [
                {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "comment": r[3] or ""}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
