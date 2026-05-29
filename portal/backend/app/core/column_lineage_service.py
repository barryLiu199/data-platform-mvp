"""字段级血缘服务 — 全量刷新

设计原则（与 lineage_service.refresh_lineage 平级、互不依赖）：
1. 单 entity 解析失败 → 写入 column_parse_failure，不影响其他 entity
2. 整体崩坏不影响表级血缘端点（不在 lineage_service 中嵌套调用）
3. manual 类型记录不参与全量清理
4. 单 SQL 解析超过 SQL_PARSE_TIMEOUT_SEC 视为 failed（避免复杂 SQL 卡住整批）
"""
from __future__ import annotations

import json as json_mod
import logging
import os
import re
import signal
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.column_lineage import ColumnLineage, ColumnParseFailure
from app.models.component import Component
from app.models.sync_task import SyncTask

logger = logging.getLogger(__name__)

SQL_PARSE_TIMEOUT_SEC = int(os.environ.get("COLUMN_LINEAGE_SQL_TIMEOUT", "5"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(name: Optional[str]) -> str:
    """字段/表名规范化 — lower、去反引号/双引号"""
    if not name:
        return ""
    return name.strip().strip('`"').lower()


def _short(s: Optional[str], n: int = 500) -> str:
    if not s:
        return ""
    return s[:n]


class _ParseTimeout(Exception):
    pass


def _with_timeout(fn, *args, timeout: int = SQL_PARSE_TIMEOUT_SEC, **kwargs):
    """SIGALRM 超时保护 — 仅在主线程 + Unix 上有效；其他场景直接 fallback"""
    try:
        def _h(signum, frame):
            raise _ParseTimeout(f"sqlglot parse exceeded {timeout}s")

        old = signal.signal(signal.SIGALRM, _h)
        signal.alarm(timeout)
        try:
            return fn(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    except (ValueError, OSError):
        # 非主线程 / Windows / signal 不可用 → 直接执行
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Parser 1: SyncTask.field_mapping
# ---------------------------------------------------------------------------

def _parse_sync_task(task: SyncTask) -> List[ColumnLineage]:
    """直接读 JSON 数组 [{kind, src, dst, type}, ...]
    kind=column 时输出 identity；kind=variable/constant 不产生上游字段。
    """
    rows: List[ColumnLineage] = []
    if not task.field_mapping or not task.source_table or not task.target_table:
        return rows
    try:
        mapping = json_mod.loads(task.field_mapping)
    except Exception:
        return rows
    if not isinstance(mapping, list):
        return rows

    src_tbl = _norm(task.source_table)
    tgt_tbl = _norm(task.target_table)

    for item in mapping:
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "column").lower()
        if kind != "column":
            continue
        src = _norm(item.get("src"))
        dst = _norm(item.get("dst"))
        if not src or not dst:
            continue
        rows.append(ColumnLineage(
            source_table=src_tbl,
            source_column=src,
            target_table=tgt_tbl,
            target_column=dst,
            source_ds_id=task.source_id,
            target_ds_id=task.target_id,
            entity_type="sync_task",
            entity_id=task.id,
            entity_name=task.name,
            transform_type="identity",
            transform_expr=None,
            parse_type="datax",
            parse_status="ok",
        ))
    return rows


# ---------------------------------------------------------------------------
# Parser 2: Component(type=sql) — sqlglot lineage
# ---------------------------------------------------------------------------

def _classify_transform(node) -> Tuple[str, Optional[str]]:
    """根据 sqlglot Node 子树判定 transform_type + 表达式字符串"""
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        return "expression", None

    expr = node.expression if hasattr(node, "expression") else None
    if expr is None:
        return "identity", None

    expr_sql = expr.sql() if hasattr(expr, "sql") else str(expr)

    # 单个 Column 引用 → identity
    if isinstance(expr, exp.Column):
        return "identity", None
    # 别名包装的纯 Column
    if isinstance(expr, exp.Alias) and isinstance(expr.this, exp.Column):
        return "identity", None
    # 含聚合函数
    if list(expr.find_all(exp.AggFunc)):
        return "aggregate", expr_sql
    # 多个不同表的 Column → join
    cols = list(expr.find_all(exp.Column))
    tables = {c.table for c in cols if c.table}
    if len(tables) > 1:
        return "join", expr_sql
    return "expression", expr_sql


def _parse_sql_columns(
    sql_text: str,
    default_target_table: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """sqlglot 列级血缘 → 边列表 [{src_table, src_col, tgt_table, tgt_col,
    transform_type, transform_expr}]"""
    import sqlglot
    from sqlglot import exp
    from sqlglot.lineage import lineage as sqlglot_lineage

    edges: List[Dict[str, Any]] = []
    statements = sqlglot.parse(sql_text, error_level=sqlglot.ErrorLevel.IGNORE)

    for stmt in statements:
        if stmt is None:
            continue

        # 仅处理 INSERT INTO ... SELECT 或 CREATE TABLE AS SELECT
        target_table: Optional[str] = None
        select_node: Optional[exp.Select] = None

        if isinstance(stmt, exp.Insert):
            tbl = stmt.this if isinstance(stmt.this, exp.Table) else stmt.find(exp.Table)
            if tbl is not None:
                target_table = tbl.name
            select_node = stmt.find(exp.Select)
        elif isinstance(stmt, exp.Create) and stmt.args.get("expression") is not None:
            tbl = stmt.find(exp.Table)
            if tbl is not None:
                target_table = tbl.name
            inner = stmt.args.get("expression")
            if isinstance(inner, exp.Select):
                select_node = inner

        if select_node is None:
            continue

        target_table = target_table or default_target_table
        if not target_table:
            continue

        target_table_n = _norm(target_table)

        # 对每个 projection 做列级血缘
        projections = select_node.expressions or []
        for idx, proj in enumerate(projections):
            tgt_col = proj.alias_or_name or f"col_{idx}"
            tgt_col_n = _norm(tgt_col)
            if not tgt_col_n or tgt_col_n == "*":
                continue

            try:
                node = sqlglot_lineage(tgt_col, sql_text)
            except Exception as e:
                logger.debug("sqlglot.lineage(%s) failed: %s", tgt_col, e)
                continue

            transform_type, transform_expr = _classify_transform(node)

            # 收集叶子节点 — downward 列引用
            leaves = []
            stack = [node]
            visited = set()
            while stack:
                n = stack.pop()
                key = id(n)
                if key in visited:
                    continue
                visited.add(key)
                if not n.downstream:
                    leaves.append(n)
                else:
                    stack.extend(n.downstream)

            for leaf in leaves:
                col_expr = leaf.expression
                if not isinstance(col_expr, exp.Column):
                    continue
                src_tbl = _norm(col_expr.table) or _norm(getattr(leaf, "source_name", "") or "")
                src_col = _norm(col_expr.name)
                if not src_tbl or not src_col:
                    continue
                edges.append({
                    "src_table": src_tbl,
                    "src_col": src_col,
                    "tgt_table": target_table_n,
                    "tgt_col": tgt_col_n,
                    "transform_type": transform_type,
                    "transform_expr": _short(transform_expr, 1000) if transform_expr else None,
                })

    # 去重（同一条边在多个 statement 重复时合并）
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for e in edges:
        k = (e["src_table"], e["src_col"], e["tgt_table"], e["tgt_col"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(e)
    return deduped


def _parse_component_sql(comp: Component) -> List[ColumnLineage]:
    cfg = comp.config_json or {}
    sql_text = (cfg.get("sql") or "").strip()
    if not sql_text:
        return []
    ds_id = cfg.get("datasource_id")

    edges = _with_timeout(_parse_sql_columns, sql_text, None)

    rows: List[ColumnLineage] = []
    for e in edges:
        rows.append(ColumnLineage(
            source_table=e["src_table"],
            source_column=e["src_col"],
            target_table=e["tgt_table"],
            target_column=e["tgt_col"],
            source_ds_id=ds_id,
            target_ds_id=ds_id,
            entity_type="component",
            entity_id=comp.id,
            entity_name=comp.name,
            transform_type=e["transform_type"],
            transform_expr=e["transform_expr"],
            parse_type="sqlglot",
            parse_status="ok",
        ))
    return rows


# ---------------------------------------------------------------------------
# Parser 3: Component(type=datax) — column array by position
# ---------------------------------------------------------------------------

def _extract_datax_columns(param: Dict[str, Any]) -> List[str]:
    """DataX column 数组可能是 ['col1', 'col2'] 或 [{'name':'col1','type':'...'}, ...]
    返回归一化后的字段名列表
    """
    cols = param.get("column", [])
    out: List[str] = []
    if not isinstance(cols, list):
        return out
    for c in cols:
        if isinstance(c, str):
            out.append(_norm(c))
        elif isinstance(c, dict):
            name = c.get("name") or c.get("Column") or ""
            out.append(_norm(name))
        else:
            out.append("")
    return out


def _parse_component_datax(comp: Component) -> List[ColumnLineage]:
    cfg = comp.config_json or {}
    raw = cfg.get("rawJson") or ""
    if not raw:
        return []
    try:
        job = json_mod.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []

    src_ds = cfg.get("source_id")
    tgt_ds = cfg.get("target_id")

    rows: List[ColumnLineage] = []
    for content in job.get("job", {}).get("content", []):
        reader_param = content.get("reader", {}).get("parameter", {}) or {}
        writer_param = content.get("writer", {}).get("parameter", {}) or {}

        # 表名（reader/writer 可能多 connection 多 table，按第一对取）
        reader_tables: List[str] = []
        for conn in reader_param.get("connection", []) or []:
            tables = conn.get("table", [])
            if isinstance(tables, str):
                tables = [tables]
            reader_tables.extend(tables)
        writer_tables: List[str] = []
        for conn in writer_param.get("connection", []) or []:
            tables = conn.get("table", [])
            if isinstance(tables, str):
                tables = [tables]
            writer_tables.extend(tables)

        if not reader_tables or not writer_tables:
            continue

        src_tbl = _norm(reader_tables[0])
        tgt_tbl = _norm(writer_tables[0])

        src_cols = _extract_datax_columns(reader_param)
        tgt_cols = _extract_datax_columns(writer_param)
        if not src_cols or not tgt_cols:
            continue

        # 按位置对齐；长度不一致按 min 截取
        n = min(len(src_cols), len(tgt_cols))
        for i in range(n):
            s = src_cols[i]
            t = tgt_cols[i]
            if not s or not t:
                continue
            rows.append(ColumnLineage(
                source_table=src_tbl,
                source_column=s,
                target_table=tgt_tbl,
                target_column=t,
                source_ds_id=src_ds,
                target_ds_id=tgt_ds,
                entity_type="component",
                entity_id=comp.id,
                entity_name=comp.name,
                transform_type="identity",
                transform_expr=None,
                parse_type="datax",
                parse_status="ok",
            ))
    return rows


# ---------------------------------------------------------------------------
# 全量刷新入口
# ---------------------------------------------------------------------------

def refresh_column_lineage(db: Session) -> Dict[str, Any]:
    """全量刷新 — manual 记录保留，其他全部重建。
    返回 stats: {sync_task, component_sql, component_datax, failed, manual_kept}
    """
    start = time.time()
    stats = {
        "sync_task": 0, "component_sql": 0, "component_datax": 0,
        "failed": 0, "manual_kept": 0, "duration_ms": 0,
    }

    # 1. 保留 manual 行，删除其余
    manual_count = db.query(ColumnLineage).filter(
        ColumnLineage.entity_type == "manual"
    ).count()
    stats["manual_kept"] = manual_count

    db.query(ColumnLineage).filter(
        ColumnLineage.entity_type != "manual"
    ).delete(synchronize_session=False)
    db.query(ColumnParseFailure).delete(synchronize_session=False)
    db.flush()

    # 2. SyncTask
    for task in db.query(SyncTask).filter(SyncTask.status == "active").all():
        try:
            edges = _parse_sync_task(task)
            if edges:
                db.bulk_save_objects(edges)
                stats["sync_task"] += len(edges)
        except Exception as e:
            stats["failed"] += 1
            logger.warning("SyncTask %s 字段血缘解析失败: %s", task.id, e)

    # 3. Component
    components = db.query(Component).filter(
        Component.status == "online",
        Component.type.in_(["sql", "datax"]),
    ).all()
    for comp in components:
        try:
            if comp.type == "sql":
                edges = _parse_component_sql(comp)
                if edges:
                    db.bulk_save_objects(edges)
                    stats["component_sql"] += len(edges)
            elif comp.type == "datax":
                edges = _parse_component_datax(comp)
                if edges:
                    db.bulk_save_objects(edges)
                    stats["component_datax"] += len(edges)
        except _ParseTimeout as e:
            stats["failed"] += 1
            db.merge(ColumnParseFailure(
                entity_type="component",
                entity_id=comp.id,
                entity_name=comp.name,
                sql_snippet=_short((comp.config_json or {}).get("sql") or ""),
                error_msg=f"timeout: {e}",
            ))
        except Exception as e:
            stats["failed"] += 1
            db.merge(ColumnParseFailure(
                entity_type="component",
                entity_id=comp.id,
                entity_name=comp.name,
                sql_snippet=_short((comp.config_json or {}).get("sql") or ""),
                error_msg=_short(str(e), 1000),
            ))

    db.commit()
    stats["duration_ms"] = int((time.time() - start) * 1000)
    return stats


# ---------------------------------------------------------------------------
# BFS — 字段视图：以 (table, column) 为中心 N 跳上下游
# ---------------------------------------------------------------------------

def build_column_lineage(
    db: Session,
    table: str,
    column: str,
    depth: int = 3,
    direction: str = "both",
) -> Dict[str, Any]:
    """返回字段级 BFS 链路 {nodes, edges}
    nodes: [{id:'col::table.column', table, column}]
    edges: [{id, source, target, transform_type, transform_expr, entity_name}]
    """
    table_n = _norm(table)
    column_n = _norm(column)

    seen_edges: set = set()
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def _add_node(t: str, c: str):
        nid = f"col::{t}.{c}"
        if nid not in nodes:
            nodes[nid] = {"id": nid, "table": t, "column": c}

    _add_node(table_n, column_n)

    def _bfs(start: List[Tuple[str, str]], up: bool):
        current = list(start)
        for _ in range(depth):
            if not current:
                break
            next_layer: List[Tuple[str, str]] = []
            if up:
                rows = db.query(ColumnLineage).filter(
                    ColumnLineage.target_table.in_([t for t, _ in current]),
                    ColumnLineage.target_column.in_([c for _, c in current]),
                ).all()
                rows = [r for r in rows
                        if (r.target_table, r.target_column) in set(current)]
                for r in rows:
                    eid = f"col_e::{r.id}"
                    if eid in seen_edges:
                        continue
                    seen_edges.add(eid)
                    _add_node(r.source_table, r.source_column)
                    edges.append({
                        "id": eid,
                        "source": f"col::{r.source_table}.{r.source_column}",
                        "target": f"col::{r.target_table}.{r.target_column}",
                        "transform_type": r.transform_type,
                        "transform_expr": r.transform_expr,
                        "entity_type": r.entity_type,
                        "entity_name": r.entity_name,
                        "parse_type": r.parse_type,
                    })
                    next_layer.append((r.source_table, r.source_column))
            else:
                rows = db.query(ColumnLineage).filter(
                    ColumnLineage.source_table.in_([t for t, _ in current]),
                    ColumnLineage.source_column.in_([c for _, c in current]),
                ).all()
                rows = [r for r in rows
                        if (r.source_table, r.source_column) in set(current)]
                for r in rows:
                    eid = f"col_e::{r.id}"
                    if eid in seen_edges:
                        continue
                    seen_edges.add(eid)
                    _add_node(r.target_table, r.target_column)
                    edges.append({
                        "id": eid,
                        "source": f"col::{r.source_table}.{r.source_column}",
                        "target": f"col::{r.target_table}.{r.target_column}",
                        "transform_type": r.transform_type,
                        "transform_expr": r.transform_expr,
                        "entity_type": r.entity_type,
                        "entity_name": r.entity_name,
                        "parse_type": r.parse_type,
                    })
                    next_layer.append((r.target_table, r.target_column))
            current = list(set(next_layer))

    if direction in ("both", "upstream"):
        _bfs([(table_n, column_n)], up=True)
    if direction in ("both", "downstream"):
        _bfs([(table_n, column_n)], up=False)

    return {
        "center": {"table": table_n, "column": column_n},
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {"total_nodes": len(nodes), "total_edges": len(edges)},
    }
