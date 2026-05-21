from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class OracleAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"oracle+oracledb://{self.ds.username}:{self._password}@{self.ds.host}:{self.ds.port}/?service_name={self._database}"

    def connect(self, db_override: Optional[str] = None):
        import oracledb
        database = db_override or self._database
        return oracledb.connect(
            user=self.ds.username, password=self.ds.password or "",
            dsn=f"{self.ds.host}:{self.ds.port or 1521}/{database}",
        )

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM all_tables WHERE owner=:1 AND table_name=:2",
            (self._database.upper(), table.upper()),
        )

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT username FROM all_users ORDER BY username")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        db = schema or self._database
        conn = self.connect(db_override=db)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name, comments FROM all_tab_comments "
                "WHERE owner=:1 ORDER BY table_name", (db.upper(),),
            )
            return [{"name": r[0], "comment": r[1] or "", "type": "BASE TABLE", "rows": 0} for r in cur.fetchall()]
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
                "SELECT column_name, data_type, nullable FROM all_tab_columns "
                "WHERE owner=:1 AND table_name=:2 ORDER BY column_id",
                (db.upper(), table.upper()),
            )
            return [
                {"name": r[0], "type": r[1], "nullable": r[2] == "Y", "comment": ""}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
