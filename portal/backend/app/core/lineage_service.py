"""血缘服务 — 全量刷新 + 以实体为中心的 BFS 图构建"""
import json as json_mod
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.lineage import TableLineage
from app.models.component import Component
from app.models.sync_task import SyncTask


# ---------------------------------------------------------------------------
# 层级推断
# ---------------------------------------------------------------------------

def _infer_layer(table_name: str) -> str:
    lower = table_name.lower()
    if lower.startswith(("ods_", "ods.")):
        return "ods"
    if lower.startswith(("dim_", "dw_", "ads_", "dim.", "dw.", "ads.")):
        return "app"
    return "source"


# ---------------------------------------------------------------------------
# SQL 解析（sqlglot，降级 regex）
# ---------------------------------------------------------------------------

def _parse_sql_tables(sql_text: str) -> Tuple[List[str], List[str]]:
    """解析 SQL 返回 (source_tables, target_tables)

    策略：sqlglot AST 解析 + regex 兜底，取并集。
    sqlglot 在处理 MySQL @变量、JSON_TABLE 等特殊语法时可能截断 AST，
    regex 能补充 sqlglot 遗漏的表名。
    """
    def _is_valid_table(name: str) -> bool:
        if not name:
            return False
        # 只允许 字母/数字/下划线/点（schema.table）
        if not re.match(r'^[\w][\w.]*$', name):
            return False
        # 过滤 MySQL 函数名（JSON_TABLE 等）
        if name.upper() in ('JSON_TABLE', 'DUAL', 'INFORMATION_SCHEMA'):
            return False
        return True

    # 1. regex 解析（始终执行，作为基础）
    regex_sources, regex_targets = _parse_sql_tables_regex(sql_text)

    # 2. sqlglot AST 解析（增强）
    ast_sources: List[str] = []
    ast_targets: List[str] = []
    try:
        import sqlglot
        from sqlglot import exp

        def _extract_table_name(tbl: exp.Table) -> Optional[str]:
            name = tbl.name
            if not name:
                return None
            db = tbl.db
            return f"{db}.{name}" if db else name

        for stmt in sqlglot.parse(sql_text, error_level=sqlglot.ErrorLevel.IGNORE):
            if stmt is None:
                continue
            if isinstance(stmt, (exp.Insert, exp.Create)):
                tbl = stmt.find(exp.Table)
                if tbl:
                    name = _extract_table_name(tbl)
                    if name:
                        ast_targets.append(name)
                for t in stmt.find_all(exp.Table):
                    n = _extract_table_name(t)
                    if n and n not in ast_targets:
                        ast_sources.append(n)
            elif isinstance(stmt, (exp.Delete, exp.Command)):
                pass
            else:
                for t in stmt.find_all(exp.Table):
                    n = _extract_table_name(t)
                    if n:
                        ast_sources.append(n)
    except Exception:
        pass

    # 3. 合并（取并集）
    all_sources = list(dict.fromkeys(regex_sources + ast_sources))
    all_targets = list(dict.fromkeys(regex_targets + ast_targets))

    # 4. 过滤
    all_sources = [s for s in all_sources if _is_valid_table(s)]
    all_targets = [t for t in all_targets if _is_valid_table(t)]

    return all_sources, all_targets


def _parse_sql_tables_regex(sql_text: str) -> Tuple[List[str], List[str]]:
    sources = re.findall(
        r'(?:FROM|JOIN)\s+[`"]?(\w+(?:\.\w+)?)[`"]?', sql_text, re.IGNORECASE
    )
    targets = re.findall(
        r'(?:INSERT\s+INTO|CREATE\s+TABLE)\s+[`"]?(\w+(?:\.\w+)?)[`"]?', sql_text, re.IGNORECASE
    )
    return list(dict.fromkeys(sources)), list(dict.fromkeys(targets))


# ---------------------------------------------------------------------------
# DataX JSON 解析
# ---------------------------------------------------------------------------

def _parse_datax_tables(raw_json) -> List[Tuple[str, str]]:
    """解析 DataX JSON → [(source_table, target_table), ...]"""
    pairs: List[Tuple[str, str]] = []
    try:
        job = json_mod.loads(raw_json) if isinstance(raw_json, str) else raw_json
        for content in job.get("job", {}).get("content", []):
            reader_param = content.get("reader", {}).get("parameter", {})
            writer_param = content.get("writer", {}).get("parameter", {})

            # reader tables: connection[].table[]  或 querySql 模式
            reader_tables: List[str] = []
            for conn in reader_param.get("connection", []):
                tables = conn.get("table", [])
                if isinstance(tables, str):
                    tables = [tables]
                reader_tables.extend(tables)

            writer_tables: List[str] = []
            for conn in writer_param.get("connection", []):
                tables = conn.get("table", [])
                if isinstance(tables, str):
                    tables = [tables]
                writer_tables.extend(tables)

            for s in reader_tables:
                for t in writer_tables:
                    if s and t:
                        pairs.append((s, t))
    except Exception:
        pass
    return pairs


# ---------------------------------------------------------------------------
# 全量刷新
# ---------------------------------------------------------------------------

def refresh_lineage(db: Session) -> Dict[str, Any]:
    start = time.time()
    stats = {"sync_tasks_parsed": 0, "components_parsed": 0, "edges_created": 0}

    # 清空旧数据
    db.query(TableLineage).delete()
    db.flush()

    edges: List[TableLineage] = []
    seen: Set[str] = set()

    def _add_edge(src: str, tgt: str, entity_type: str, entity_id: int,
                  entity_name: str, parse_type: str,
                  source_ds_id: Optional[int] = None,
                  target_ds_id: Optional[int] = None):
        key = f"{src}→{tgt}→{entity_type}→{entity_id}"
        if key in seen:
            return
        seen.add(key)
        edges.append(TableLineage(
            source_table=src, target_table=tgt,
            source_ds_id=source_ds_id, target_ds_id=target_ds_id,
            entity_type=entity_type, entity_id=entity_id,
            entity_name=entity_name, parse_type=parse_type,
        ))

    # 1. SyncTask
    sync_tasks = db.query(SyncTask).filter(SyncTask.status == "active").all()
    for t in sync_tasks:
        if t.source_table and t.target_table:
            _add_edge(
                t.source_table, t.target_table,
                "sync_task", t.id, t.name, "datax",
                source_ds_id=t.source_id, target_ds_id=t.target_id,
            )
            stats["sync_tasks_parsed"] += 1

    # 2. Component (online)
    components = db.query(Component).filter(Component.status == "online").all()
    for c in components:
        cfg = c.config_json or {}
        if c.type == "datax":
            raw = cfg.get("rawJson", "")
            if raw:
                for src, tgt in _parse_datax_tables(raw):
                    src_ds = cfg.get("source_id")
                    tgt_ds = cfg.get("target_id")
                    _add_edge(src, tgt, "component", c.id, c.name, "datax",
                              source_ds_id=src_ds, target_ds_id=tgt_ds)
                stats["components_parsed"] += 1
        elif c.type == "sql":
            sql_text = cfg.get("sql", "")
            if sql_text:
                sources, targets = _parse_sql_tables(sql_text)
                ds_id = cfg.get("datasource_id")
                parse_type = "sql_ast"
                for tgt in targets:
                    for src in sources:
                        _add_edge(src, tgt, "component", c.id, c.name,
                                  parse_type, source_ds_id=ds_id, target_ds_id=ds_id)
                # 如果没有 INSERT/CREATE，但 SQL 里有 FROM → 仍记录，source=来源表，无 target
                if not targets and sources:
                    pass  # Phase 2: 可考虑记录只读引用
                stats["components_parsed"] += 1

    # 批量写入
    if edges:
        db.add_all(edges)
    db.commit()

    stats["edges_created"] = len(edges)
    stats["duration_ms"] = int((time.time() - start) * 1000)
    return stats


# ---------------------------------------------------------------------------
# BFS 图构建 + 水平分层布局
# ---------------------------------------------------------------------------

COLUMN_GAP = 300
ROW_GAP = 120
NODE_HEIGHT = 72


def build_lineage_graph(
    db: Session,
    entity_type: str,
    entity_id,
    depth: int = 2,
) -> Dict[str, Any]:
    """以实体为中心构建血缘图，返回 Vue Flow nodes + edges"""

    # 1. 确定中心表集合
    #    中心 = 该组件/任务的 target 表（INSERT INTO 的目标）
    #    source 表属于上游，通过 BFS 自然展现
    center_tables: Set[str] = set()

    if entity_type == "table":
        center_tables.add(str(entity_id))  # entity_id 就是表名
    else:
        rows = db.query(TableLineage).filter(
            TableLineage.entity_type == entity_type,
            TableLineage.entity_id == int(entity_id),
        ).all()
        for r in rows:
            center_tables.add(r.target_table)

    if not center_tables:
        return {"nodes": [], "edges": [], "center_tables": [], "stats": {
            "total_nodes": 0, "total_edges": 0, "upstream_depth": 0, "downstream_depth": 0
        }}

    # 2. BFS 上游
    all_tables: Dict[str, int] = {}  # table_name → level (0=center, -1=上游1层, ...)
    for t in center_tables:
        all_tables[t] = 0

    all_lineage_rows: List[TableLineage] = []
    used_edges: Set[str] = set()

    # 上游 BFS
    current_layer = set(center_tables)
    for d in range(1, depth + 1):
        if not current_layer:
            break
        rows = db.query(TableLineage).filter(
            TableLineage.target_table.in_(current_layer)
        ).all()
        next_layer: Set[str] = set()
        for r in rows:
            edge_key = f"{r.source_table}→{r.target_table}→{r.id}"
            if edge_key not in used_edges:
                used_edges.add(edge_key)
                all_lineage_rows.append(r)
            if r.source_table not in all_tables:
                all_tables[r.source_table] = -d
                next_layer.add(r.source_table)
        current_layer = next_layer

    # 下游 BFS
    current_layer = set(center_tables)
    for d in range(1, depth + 1):
        if not current_layer:
            break
        rows = db.query(TableLineage).filter(
            TableLineage.source_table.in_(current_layer)
        ).all()
        next_layer: Set[str] = set()
        for r in rows:
            edge_key = f"{r.source_table}→{r.target_table}→{r.id}"
            if edge_key not in used_edges:
                used_edges.add(edge_key)
                all_lineage_rows.append(r)
            if r.target_table not in all_tables:
                all_tables[r.target_table] = d
                next_layer.add(r.target_table)
        current_layer = next_layer

    # 3. 收集表的数据源信息
    table_ds: Dict[str, Optional[int]] = {}
    ds_name_cache: Dict[int, str] = {}

    for r in all_lineage_rows:
        if r.source_table not in table_ds and r.source_ds_id:
            table_ds[r.source_table] = r.source_ds_id
        if r.target_table not in table_ds and r.target_ds_id:
            table_ds[r.target_table] = r.target_ds_id

    # 批量查数据源名称
    ds_ids = set(v for v in table_ds.values() if v)
    if ds_ids:
        from app.models.datasource import DataSource
        ds_rows = db.query(DataSource.id, DataSource.name).filter(
            DataSource.id.in_(ds_ids)
        ).all()
        ds_name_cache = {r.id: r.name for r in ds_rows}

    # 4. 水平分层布局
    levels: Dict[int, List[str]] = defaultdict(list)
    for tbl, level in all_tables.items():
        levels[level].append(tbl)
    for level in levels:
        levels[level].sort()

    min_level = min(levels.keys()) if levels else 0
    max_group_size = max(len(v) for v in levels.values()) if levels else 0

    nodes = []
    for tbl, level in all_tables.items():
        group = levels[level]
        row_idx = group.index(tbl)
        group_size = len(group)
        # 垂直居中
        y_offset = (max_group_size - group_size) * ROW_GAP / 2
        x = (level - min_level) * COLUMN_GAP
        y = row_idx * ROW_GAP + y_offset

        ds_id = table_ds.get(tbl)
        ds_name = ds_name_cache.get(ds_id, "") if ds_id else ""

        nodes.append({
            "id": f"table::{tbl}",
            "type": "lineage-table",
            "position": {"x": x, "y": y},
            "data": {
                "tableName": tbl,
                "layer": _infer_layer(tbl),
                "datasourceName": ds_name,
                "datasourceId": ds_id,
                "isCenter": tbl in center_tables,
                "columns": [],
            }
        })

    # 5. 构建 edges（按 source_table→target_table 去重合并 label）
    edge_map: Dict[str, Dict] = {}
    for r in all_lineage_rows:
        key = f"{r.source_table}→{r.target_table}"
        if key not in edge_map:
            edge_map[key] = {
                "id": f"e::{r.source_table}::{r.target_table}",
                "source": f"table::{r.source_table}",
                "target": f"table::{r.target_table}",
                "sourceHandle": "right",
                "targetHandle": "left",
                "label": f"{r.entity_name} ({r.parse_type})" if r.entity_name else "",
                "animated": False,
                "data": {
                    "entityType": r.entity_type,
                    "entityId": r.entity_id,
                    "entityName": r.entity_name,
                    "parseType": r.parse_type,
                },
            }
        else:
            # 多个实体产生同一条表→表关系，合并 label
            existing = edge_map[key]
            existing_label = existing["label"]
            new_label = f"{r.entity_name} ({r.parse_type})" if r.entity_name else ""
            if new_label and new_label not in existing_label:
                existing["label"] = f"{existing_label}, {new_label}"

    edges = list(edge_map.values())

    upstream_depth = abs(min_level) if min_level < 0 else 0
    downstream_depth = max(levels.keys()) if levels else 0

    return {
        "nodes": nodes,
        "edges": edges,
        "center_tables": list(center_tables),
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "upstream_depth": upstream_depth,
            "downstream_depth": downstream_depth,
        }
    }
