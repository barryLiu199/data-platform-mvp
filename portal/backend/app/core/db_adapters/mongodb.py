from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class MongoDBAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        raise ValueError("MongoDB does not support SQLAlchemy URLs")

    def connect(self, db_override: Optional[str] = None):
        from pymongo import MongoClient
        database = db_override or self._database
        uri = f"mongodb://{self.ds.username}:{self.ds.password}@{self.ds.host}:{self.ds.port or 27017}/{database}"
        return MongoClient(uri, serverSelectionTimeoutMS=5000)

    def test_connection(self, table: Optional[str] = None) -> Tuple[bool, str]:
        try:
            conn = self.connect()
            try:
                conn.admin.command("ping")
                if table:
                    db = conn[self._database]
                    if table not in db.list_collection_names():
                        return False, f"集合 {table} 不存在"
            finally:
                conn.close()
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {e}"

    def list_databases(self) -> List[str]:
        conn = self.connect()
        try:
            return [d for d in conn.list_database_names() if d not in ("admin", "config", "local")]
        finally:
            conn.close()

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        db_name = schema or self._database
        conn = self.connect()
        try:
            mdb = conn[db_name]
            return [
                {"name": n, "comment": "", "type": "COLLECTION", "rows": mdb[n].estimated_document_count()}
                for n in mdb.list_collection_names()
            ]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        db_name = schema or self._database
        conn = self.connect()
        try:
            mdb = conn[db_name]
            doc = mdb[table].find_one() or {}
            return [
                {"name": k, "type": type(v).__name__, "nullable": True, "comment": ""}
                for k, v in doc.items()
            ]
        finally:
            conn.close()
