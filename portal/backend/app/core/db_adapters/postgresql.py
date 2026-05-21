import re
from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class PostgresqlAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg2://{self.ds.username}:{self._password}@{self.ds.host}:{self.ds.port}/{self._database}"

    def connect(self, db_override: Optional[str] = None):
        import psycopg2
        database = db_override or self._database
        conn = psycopg2.connect(
            host=self.ds.host, port=self.ds.port or 5432, user=self.ds.username,
            password=self.ds.password, dbname=database, connect_timeout=5,
        )
        cur = conn.cursor()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', database):
            raise ValueError(f"Invalid database name: {database}")
        cur.execute(f"SET search_path TO {database}, public")
        cur.close()
        return conn

    def _table_exists_query(self, table: str) -> Tuple[str, tuple]:
        return (
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_catalog=%s AND table_name=%s",
            (self._database, table),
        )

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate=false")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT t.table_schema, t.table_name, d.description, t.table_type, "
                "COALESCE(c.reltuples::bigint, 0) "
                "FROM information_schema.tables t "
                "LEFT JOIN pg_catalog.pg_class c ON c.relname = t.table_name "
                "LEFT JOIN pg_catalog.pg_description d ON d.objoid = c.oid AND d.objsubid = 0 "
                "WHERE t.table_schema NOT IN ('pg_catalog','information_schema') ORDER BY t.table_name"
            )
            return [
                {
                    "name": f"{r[0]}.{r[1]}" if r[0] != "public" else r[1],
                    "comment": r[2] or "",
                    "type": "BASE TABLE" if r[3] == "BASE TABLE" else (r[3] or "BASE TABLE"),
                    "rows": int(r[4] or 0),
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        if "." in table:
            schema, table = table.split(".", 1)
        conn = self.connect()
        try:
            cur = conn.cursor()
            if schema:
                cur.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                    "ORDER BY ordinal_position", (schema, table),
                )
            else:
                cur.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name=%s "
                    "ORDER BY ordinal_position", (table,),
                )
            return [
                {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "comment": ""}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
