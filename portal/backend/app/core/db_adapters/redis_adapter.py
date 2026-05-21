from typing import List, Dict, Any, Optional, Tuple
from app.core.db_adapters import AdapterBase


class RedisAdapter(AdapterBase):

    def sqlalchemy_url(self) -> str:
        raise ValueError("Redis does not support SQLAlchemy URLs")

    def connect(self, db_override: Optional[str] = None):
        import redis
        return redis.Redis(
            host=self.ds.host, port=self.ds.port or 6379, password=self.ds.password or None,
            decode_responses=True, socket_connect_timeout=5,
        )

    def test_connection(self, table: Optional[str] = None) -> Tuple[bool, str]:
        try:
            conn = self.connect()
            conn.ping()
            conn.close()
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {e}"

    def list_databases(self) -> List[str]:
        return ["0"]

    def list_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            keys = conn.keys("*")[:100]
            return [{"name": k, "comment": "", "type": "KEY", "rows": 0} for k in keys]
        finally:
            conn.close()

    def list_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            t = conn.type(table)
            if t == "hash":
                fields = conn.hkeys(table)
                return [{"name": f, "type": "string", "nullable": True, "comment": ""} for f in fields]
            return [{"name": "value", "type": t, "nullable": True, "comment": ""}]
        finally:
            conn.close()
