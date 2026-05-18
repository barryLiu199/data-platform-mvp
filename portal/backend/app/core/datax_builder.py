"""DataX JSON 配置生成器

把 Portal 的同步任务模型翻译为 DataX 引擎能直接消费的 job.json。
v1 支持 MySQL ↔ MySQL，后续可扩展 PostgreSQL/Hive/Oracle。
"""
from typing import List, Dict, Any, Optional

from app.models.datasource import DataSource


# ---- 类型映射 ----
# 数据源 type 字段 → DataX reader / writer 名
_READER_MAP = {
    "mysql": "mysqlreader",
    "postgresql": "postgresqlreader",
    "oracle": "oraclereader",
    "sqlserver": "sqlserverreader",
    "clickhouse": "clickhousereader",
    "mongodb": "mongodbreader",
    "hive": "hivereader",
}

_WRITER_MAP = {
    "mysql": "mysqlwriter",
    "postgresql": "postgresqlwriter",
    "oracle": "oraclewriter",
    "sqlserver": "sqlserverwriter",
    "clickhouse": "clickhousewriter",
    "mongodb": "mongodbwriter",
    "hive": "hivewriter",
}


def _jdbc_url(ds: DataSource) -> str:
    """构造 JDBC URL"""
    t = (ds.type or "").lower()
    if t == "mysql":
        return f"jdbc:mysql://{ds.host}:{ds.port}/{ds.database_name}?useUnicode=true&characterEncoding=utf-8&useSSL=false&serverTimezone=Asia/Shanghai"
    if t == "postgresql":
        return f"jdbc:postgresql://{ds.host}:{ds.port}/{ds.database_name}"
    if t == "oracle":
        return f"jdbc:oracle:thin:@{ds.host}:{ds.port}:{ds.database_name}"
    if t == "sqlserver":
        return f"jdbc:sqlserver://{ds.host}:{ds.port};DatabaseName={ds.database_name}"
    if t == "clickhouse":
        return f"jdbc:clickhouse://{ds.host}:{ds.port}/{ds.database_name}"
    if t == "hive":
        return f"jdbc:hive2://{ds.host}:{ds.port}/{ds.database_name}"
    raise ValueError(f"不支持的数据源类型: {ds.type}")


def _reader_name(ds: DataSource) -> str:
    t = (ds.type or "").lower()
    if t not in _READER_MAP:
        raise ValueError(f"DataX 暂不支持读取 {ds.type}")
    return _READER_MAP[t]


def _writer_name(ds: DataSource) -> str:
    t = (ds.type or "").lower()
    if t not in _WRITER_MAP:
        raise ValueError(f"DataX 暂不支持写入 {ds.type}")
    return _WRITER_MAP[t]


def build_datax_job(
    source_ds: DataSource,
    source_table: str,
    target_ds: DataSource,
    target_table: str,
    field_mapping: List[Dict[str, Any]],
    sync_type: str = "full",
    increment_column: Optional[str] = None,
    where_clause: Optional[str] = None,
    split_pk: Optional[str] = None,
    write_mode: str = "insert",
    pre_sql: Optional[List[str]] = None,
    post_sql: Optional[List[str]] = None,
    truncate_before_write: bool = True,
    channel: int = 3,
    mask_password: bool = True,
) -> Dict[str, Any]:
    """生成 DataX job.json 字典

    field_mapping 元素结构（向下兼容，缺 kind 时按 column 处理）：
      {"kind": "column",    "src": "name",         "dst": "user_name"}
      {"kind": "constant",  "src": "CN",           "dst": "region"}
      {"kind": "variable",  "src": "${bizdate}",   "dst": "dt"}
    DataX reader.column 数组支持「字段名 (str) | {type,value} (dict)」混合元素。

    Args:
        sync_type: full / increment
        increment_column: 增量列；当未提供 where_clause 时由它生成默认 WHERE
        where_clause: 用户自定义 WHERE 条件，优先级高于 increment_column 生成的
        split_pk: 多通道并发切分键；不传则尝试用第一个 column 字段
        write_mode: insert / replace / update (mysqlwriter 原生支持)
        pre_sql / post_sql: 写入前/后在目标库执行的 SQL 列表
        truncate_before_write: sync_type=full 且未传 pre_sql 时自动加 TRUNCATE
        mask_password: 预览时 True，实际下发 False
    """
    if not field_mapping:
        raise ValueError("字段映射不能为空")

    # ---- 拆解 reader column / writer column ----
    reader_columns: List[Any] = []
    writer_columns: List[str] = []
    first_real_col: Optional[str] = None
    for m in field_mapping:
        kind = (m.get("kind") or "column").lower()
        src = m.get("src", "")
        dst = m.get("dst", "")
        if not dst:
            continue
        writer_columns.append(dst)
        if kind == "column":
            reader_columns.append(src)
            if first_real_col is None:
                first_real_col = src
        elif kind in ("constant", "variable"):
            # DataX 数据透传方式：{type, value}；变量交由调度器在执行时替换
            reader_columns.append({"type": "string", "value": src})
        else:
            # 未知 kind 当 column 处理
            reader_columns.append(src)
            if first_real_col is None:
                first_real_col = src

    if not reader_columns:
        raise ValueError("字段映射无有效项")

    def _pw(p: Optional[str]) -> str:
        if not p:
            return ""
        return "******" if mask_password else p

    # ---- reader ----
    reader_param: Dict[str, Any] = {
        "username": source_ds.username or "",
        "password": _pw(source_ds.password),
        "column": reader_columns,
        "connection": [{
            "jdbcUrl": [_jdbc_url(source_ds)],
            "table": [source_table],
        }],
    }
    # splitPk：用户传入优先，否则尝试第一个真实列
    sp = split_pk or first_real_col
    if sp:
        reader_param["splitPk"] = sp

    # WHERE：用户自定义 > 增量自动生成
    final_where = where_clause
    if not final_where and sync_type == "increment":
        if not increment_column:
            raise ValueError("增量同步必须指定 increment_column 或 where_clause")
        final_where = f"{increment_column} > '${{last_sync_time}}'"
    if final_where:
        reader_param["where"] = final_where

    reader = {"name": _reader_name(source_ds), "parameter": reader_param}

    # ---- writer ----
    writer_param: Dict[str, Any] = {
        "username": target_ds.username or "",
        "password": _pw(target_ds.password),
        "column": writer_columns,
        "writeMode": write_mode or "insert",
        "connection": [{
            "jdbcUrl": _jdbc_url(target_ds),
            "table": [target_table],
        }],
    }

    # preSql / postSql：用户显式传入优先；否则全量同步自动 TRUNCATE
    effective_pre = [s for s in (pre_sql or []) if s and s.strip()]
    if not effective_pre and sync_type == "full" and truncate_before_write:
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', target_table):
            raise ValueError(f"Invalid target table name: {target_table}")
        effective_pre = [f"TRUNCATE TABLE {target_table}"]
    if effective_pre:
        writer_param["preSql"] = effective_pre

    effective_post = [s for s in (post_sql or []) if s and s.strip()]
    if effective_post:
        writer_param["postSql"] = effective_post

    writer = {"name": _writer_name(target_ds), "parameter": writer_param}

    # ---- job ----
    return {
        "job": {
            "content": [{"reader": reader, "writer": writer}],
            "setting": {
                "speed": {"channel": channel},
                "errorLimit": {"record": 0, "percentage": 0.02},
            },
        }
    }


def build_for_sync_task(task, source_ds: DataSource, target_ds: DataSource, mask_password: bool = True) -> Dict[str, Any]:
    """便捷封装：直接基于 SyncTask 模型生成 DataX 配置"""
    import json

    def _load(s):
        if not s:
            return None
        try:
            return json.loads(s) if isinstance(s, str) else s
        except Exception:
            return None

    fm = _load(task.field_mapping)
    if not fm:
        raise ValueError("任务未配置字段映射")
    return build_datax_job(
        source_ds=source_ds,
        source_table=task.source_table,
        target_ds=target_ds,
        target_table=task.target_table,
        field_mapping=fm,
        sync_type=task.sync_type or "full",
        increment_column=task.increment_column,
        where_clause=task.where_clause,
        split_pk=task.split_pk,
        write_mode=task.write_mode or "insert",
        channel=task.channel or 3,
        pre_sql=_load(task.pre_sql),
        post_sql=_load(task.post_sql),
        mask_password=mask_password,
    )
