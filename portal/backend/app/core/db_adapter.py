"""通用数据库适配器

为多种数据源类型（MySQL / PostgreSQL / SQLServer / Oracle / ClickHouse / MongoDB / Redis / Hive）
提供统一的连接、SQL 执行、元数据查询接口。

使用方式：
    from app.core.db_adapter import test_connection, sqlalchemy_url, list_tables
    ok, msg = test_connection(ds, table="users")
"""
from typing import List, Dict, Any, Optional, Tuple

from app.models.datasource import DataSource


# ---- SQLAlchemy URL ----

def sqlalchemy_url(ds: DataSource) -> str:
    """生成 SQLAlchemy 连接 URL。
    不支持的类型抛 ValueError。
    """
    t = (ds.type or "").lower()
    pwd = ds.password or ""
    if t == "mysql":
        return f"mysql+pymysql://{ds.username}:{pwd}@{ds.host}:{ds.port}/{ds.database_name}?charset=utf8mb4"
    if t == "postgresql":
        return f"postgresql+psycopg2://{ds.username}:{pwd}@{ds.host}:{ds.port}/{ds.database_name}"
    if t == "sqlserver":
        return f"mssql+pymssql://{ds.username}:{pwd}@{ds.host}:{ds.port}/{ds.database_name}"
    if t == "oracle":
        return f"oracle+oracledb://{ds.username}:{pwd}@{ds.host}:{ds.port}/?service_name={ds.database_name}"
    if t == "clickhouse":
        return f"clickhouse+native://{ds.username}:{pwd}@{ds.host}:{ds.port}/{ds.database_name}"
    if t == "hive":
        return f"hive://{ds.username}@{ds.host}:{ds.port}/{ds.database_name}"
    raise ValueError(f"SQLAlchemy 不支持的数据源类型: {ds.type}")


# ---- 原生连接 ----

def _connect(ds: DataSource, db_override: Optional[str] = None):
    """获取原生数据库连接对象（不同库返回不同对象）。
    调用方负责 close。
    """
    t = (ds.type or "").lower()
    database = db_override or ds.database_name

    if t == "mysql":
        import pymysql
        return pymysql.connect(
            host=ds.host, port=ds.port or 3306, user=ds.username,
            password=ds.password, database=database, connect_timeout=5,
            charset="utf8mb4",
        )
    if t == "postgresql":
        import psycopg2
        conn = psycopg2.connect(
            host=ds.host, port=ds.port or 5432, user=ds.username,
            password=ds.password, dbname=database, connect_timeout=5,
        )
        # 设置 search_path 到当前数据库 schema，确保表查询能找到
        cur = conn.cursor()
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', database):
            raise ValueError(f"Invalid database name: {database}")
        cur.execute(f"SET search_path TO {database}, public")
        cur.close()
        return conn
    if t == "sqlserver":
        import pymssql
        return pymssql.connect(
            server=ds.host, port=str(ds.port or 1433), user=ds.username,
            password=ds.password, database=database, login_timeout=5,
        )
    if t == "oracle":
        import oracledb
        return oracledb.connect(
            user=ds.username, password=ds.password or "",
            dsn=f"{ds.host}:{ds.port or 1521}/{database}",
        )
    if t == "clickhouse":
        from clickhouse_driver import Client
        return Client(
            host=ds.host, port=ds.port or 9000,
            user=ds.username or "default", password=ds.password or "",
            database=database,
        )
    if t == "mongodb":
        from pymongo import MongoClient
        uri = f"mongodb://{ds.username}:{ds.password}@{ds.host}:{ds.port or 27017}/{database}"
        return MongoClient(uri, serverSelectionTimeoutMS=5000)
    if t == "redis":
        import redis
        return redis.Redis(
            host=ds.host, port=ds.port or 6379, password=ds.password or None,
            decode_responses=True, socket_connect_timeout=5,
        )
    if t == "hive":
        from impala.dbapi import connect
        return connect(
            host=ds.host, port=ds.port or 10000, user=ds.username,
            password=ds.password or "", database=database,
            auth_mechanism="PLAIN", timeout=5,
        )
    raise ValueError(f"不支持的数据源类型: {ds.type}")


# ---- 测试连接 ----

def test_connection(ds: DataSource, table: Optional[str] = None) -> Tuple[bool, str]:
    """通用连接测试。table 非空时额外验证表存在。
    返回 (ok, message)。
    """
    t = (ds.type or "").lower()
    try:
        conn = _connect(ds)
        try:
            if t == "clickhouse":
                conn.execute("SELECT 1")
                if table:
                    res = conn.execute(
                        "SELECT count() FROM system.tables WHERE database=%(db)s AND name=%(t)s",
                        {"db": ds.database_name, "t": table},
                    )
                    if not res or res[0][0] == 0:
                        return False, f"表 {table} 不存在"
            elif t == "mongodb":
                conn.admin.command("ping")
                if table:
                    db = conn[ds.database_name]
                    if table not in db.list_collection_names():
                        return False, f"集合 {table} 不存在"
            elif t == "redis":
                conn.ping()
            else:
                # MySQL / PostgreSQL / SQLServer / Oracle / Hive
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                if table:
                    sql, params = _table_exists_query(t, ds.database_name, table)
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


def _table_exists_query(db_type: str, schema: str, table: str):
    """各 SQL 数据库的表存在性查询"""
    if db_type == "mysql":
        return (
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (schema, table),
        )
    if db_type == "postgresql":
        return (
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_catalog=%s AND table_name=%s",
            (schema, table),
        )
    if db_type == "sqlserver":
        return (
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_CATALOG=%s AND TABLE_NAME=%s",
            (schema, table),
        )
    if db_type == "oracle":
        return (
            "SELECT COUNT(*) FROM all_tables WHERE owner=:1 AND table_name=:2",
            (schema.upper(), table.upper()),
        )
    if db_type == "hive":
        return (
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema=? AND table_name=?",
            (schema, table),
        )
    raise ValueError(f"未实现的表存在性查询: {db_type}")


# ---- 元数据查询 ----

def list_databases(ds: DataSource) -> List[str]:
    """列出所有数据库 / schema"""
    t = (ds.type or "").lower()
    conn = _connect(ds)
    try:
        if t == "mysql":
            cur = conn.cursor()
            cur.execute("SHOW DATABASES")
            return [r[0] for r in cur.fetchall() if r[0] not in ("information_schema", "mysql", "performance_schema", "sys")]
        if t == "postgresql":
            cur = conn.cursor()
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate=false")
            return [r[0] for r in cur.fetchall()]
        if t == "sqlserver":
            cur = conn.cursor()
            cur.execute("SELECT name FROM sys.databases WHERE database_id > 4")
            return [r[0] for r in cur.fetchall()]
        if t == "oracle":
            cur = conn.cursor()
            cur.execute("SELECT username FROM all_users ORDER BY username")
            return [r[0] for r in cur.fetchall()]
        if t == "clickhouse":
            res = conn.execute("SHOW DATABASES")
            return [r[0] for r in res if r[0] not in ("system", "INFORMATION_SCHEMA", "information_schema")]
        if t == "mongodb":
            return [d for d in conn.list_database_names() if d not in ("admin", "config", "local")]
        if t == "hive":
            cur = conn.cursor()
            cur.execute("SHOW DATABASES")
            return [r[0] for r in cur.fetchall()]
        raise ValueError(f"不支持列出数据库: {t}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_tables(ds: DataSource, schema: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出指定 schema 下的表。返回 [{name, comment}]"""
    t = (ds.type or "").lower()
    db = schema or ds.database_name
    conn = _connect(ds, db_override=db)
    try:
        if t == "mysql":
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_TYPE, COALESCE(TABLE_ROWS, 0) "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME", (db,),
            )
            return [{"name": r[0], "comment": r[1] or "", "type": r[2] or "BASE TABLE", "rows": int(r[3] or 0)} for r in cur.fetchall()]
        if t == "postgresql":
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
        if t == "sqlserver":
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
            )
            return [{"name": r[0], "comment": "", "type": r[1] or "BASE TABLE", "rows": 0} for r in cur.fetchall()]
        if t == "oracle":
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name, comments FROM all_tab_comments "
                "WHERE owner=:1 ORDER BY table_name", (db.upper(),),
            )
            return [{"name": r[0], "comment": r[1] or "", "type": "BASE TABLE", "rows": 0} for r in cur.fetchall()]
        if t == "clickhouse":
            res = conn.execute(
                "SELECT name, comment, total_rows FROM system.tables WHERE database=%(db)s ORDER BY name",
                {"db": db},
            )
            return [{"name": r[0], "comment": r[1] or "", "type": "BASE TABLE", "rows": int(r[2] or 0)} for r in res]
        if t == "mongodb":
            mdb = conn[db]
            return [
                {"name": n, "comment": "", "type": "COLLECTION", "rows": mdb[n].estimated_document_count()}
                for n in mdb.list_collection_names()
            ]
        if t == "hive":
            cur = conn.cursor()
            cur.execute("SHOW TABLES")
            return [{"name": r[0], "comment": "", "type": "BASE TABLE", "rows": 0} for r in cur.fetchall()]
        raise ValueError(f"不支持列出表: {t}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_columns(ds: DataSource, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出表字段。返回 [{name, type, nullable, comment}]"""
    t = (ds.type or "").lower()
    # 支持 schema.table 格式
    if "." in table:
        schema, table = table.split(".", 1)
    db = schema or ds.database_name
    conn = _connect(ds, db_override=db if t != "postgresql" else None)
    try:
        if t == "mysql":
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
        if t == "postgresql":
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
        if t == "sqlserver":
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
        if t == "oracle":
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
        if t == "clickhouse":
            res = conn.execute(
                "SELECT name, type, comment FROM system.columns "
                "WHERE database=%(db)s AND table=%(t)s ORDER BY position",
                {"db": db, "t": table},
            )
            return [
                {"name": r[0], "type": r[1], "nullable": "Nullable" in r[1], "comment": r[2] or ""}
                for r in res
            ]
        if t == "mongodb":
            mdb = conn[db]
            doc = mdb[table].find_one() or {}
            return [
                {"name": k, "type": type(v).__name__, "nullable": True, "comment": ""}
                for k, v in doc.items()
            ]
        if t == "hive":
            cur = conn.cursor()
            import re
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', table):
                raise ValueError(f"Invalid table name: {table}")
            cur.execute(f"DESCRIBE {table}")
            return [
                {"name": r[0], "type": r[1], "nullable": True, "comment": r[2] or ""}
                for r in cur.fetchall()
            ]
        raise ValueError(f"不支持列出字段: {t}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
