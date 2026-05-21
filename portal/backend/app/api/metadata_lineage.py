"""元数据血缘端点 — 从 metadata.py 拆分

包含：
  - GET /lineage          — v1 自动解析血缘
  - GET /lineage/entities — v2 实体列表
  - GET /lineage/{entity_type}/{entity_id} — v2 血缘图
  - POST /lineage/refresh — 全量刷新
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["元数据-血缘"])


# ===== 血缘 v1 =====
@router.get("/lineage")
def get_lineage(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """自动解析组件/同步任务生成表级血缘"""
    from app.models.component import Component
    from app.models.sync_task import SyncTask
    import json as json_mod

    nodes_map = {}  # table_name → node info
    edges = []

    def add_node(name, ds_name=None):
        if not name or name in nodes_map:
            return
        # 推断层级
        lower = name.lower()
        if lower.startswith("ods_") or lower.startswith("ods."):
            layer = "ods"
        elif lower.startswith(("dim_", "dw_", "ads_", "dim.", "dw.", "ads.")):
            layer = "app"
        else:
            layer = "source"
        nodes_map[name] = {"id": name, "name": name, "datasource": ds_name, "layer": layer}

    # 1. SyncTask — 直接有 source_table / target_table
    sync_tasks = db.query(SyncTask).filter(SyncTask.status == "active").all()
    for t in sync_tasks:
        src = t.source_table
        tgt = t.target_table
        if src and tgt:
            add_node(src, "source")
            add_node(tgt, "target")
            edges.append({"source": src, "target": tgt, "type": "DataX", "task_name": t.name})

    # 2. Component (online) — 解析 SQL 和 DataX
    components = db.query(Component).filter(Component.status == "online").all()
    for c in components:
        cfg = c.config_json or {}
        if c.type == "datax":
            # 从 rawJson 解析 reader/writer table
            raw = cfg.get("rawJson", "")
            if raw:
                try:
                    job = json_mod.loads(raw) if isinstance(raw, str) else raw
                    content = job.get("job", {}).get("content", [{}])[0]
                    reader_tables = (content.get("reader", {}).get("parameter", {})
                                     .get("connection", [{}])[0].get("table", []))
                    writer_tables = (content.get("writer", {}).get("parameter", {})
                                     .get("connection", [{}])[0].get("table", []))
                    for st in (reader_tables if isinstance(reader_tables, list) else [reader_tables]):
                        for tt in (writer_tables if isinstance(writer_tables, list) else [writer_tables]):
                            if st and tt:
                                add_node(st)
                                add_node(tt)
                                edges.append({"source": st, "target": tt, "type": "DataX", "task_name": c.name})
                except Exception as e:
                    logger.warning("DataX lineage parse failed for component %s: %s", c.name, e)
        elif c.type == "sql":
            # 简单正则提取 FROM/JOIN/INSERT INTO
            sql_text = cfg.get("sql", "")
            if sql_text:
                import re
                # 提取 source tables (FROM / JOIN)
                sources = re.findall(
                    r'(?:FROM|JOIN)\s+[`"]?(\w+)[`"]?', sql_text, re.IGNORECASE
                )
                # 提取 target table (INSERT INTO / CREATE TABLE)
                targets = re.findall(
                    r'(?:INSERT\s+INTO|CREATE\s+TABLE)\s+[`"]?(\w+)[`"]?', sql_text, re.IGNORECASE
                )
                for s in sources:
                    add_node(s)
                for t in targets:
                    add_node(t)
                    for s in sources:
                        edges.append({"source": s, "target": t, "type": "SQL", "task_name": c.name})

    # 去重 edges
    seen = set()
    unique_edges = []
    for e in edges:
        key = f"{e['source']}→{e['target']}"
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return {
        "nodes": list(nodes_map.values()),
        "edges": unique_edges,
    }


# ===== 血缘 v2 =====

@router.get("/lineage/entities")
def get_lineage_entities(
    type: str = Query(..., description="component_sql / component_datax / sync_task / table"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """返回实体列表供下拉框选择"""
    from app.models.component import Component as Comp
    from app.models.sync_task import SyncTask as ST
    from app.models.lineage import TableLineage

    if type == "component_sql":
        rows = db.query(Comp).filter(Comp.type == "sql", Comp.status == "online").all()
        return [{"id": r.id, "name": r.name, "sub_type": "sql", "status": r.status} for r in rows]
    elif type == "component_datax":
        rows = db.query(Comp).filter(Comp.type == "datax", Comp.status == "online").all()
        return [{"id": r.id, "name": r.name, "sub_type": "datax", "status": r.status} for r in rows]
    elif type == "sync_task":
        rows = db.query(ST).filter(ST.status == "active").all()
        return [{"id": r.id, "name": r.name, "status": r.status} for r in rows]
    elif type == "table":
        # 所有出现过的表名
        src = db.query(TableLineage.source_table).distinct().all()
        tgt = db.query(TableLineage.target_table).distinct().all()
        tables = sorted(set(r[0] for r in src) | set(r[0] for r in tgt))
        return [{"id": t, "name": t} for t in tables]
    else:
        raise HTTPException(400, f"不支持的实体类型: {type}")


@router.get("/lineage/{entity_type}/{entity_id}")
def get_lineage_graph(
    entity_type: str,
    entity_id: str,
    depth: int = Query(2, ge=1, le=5),
    field_level: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """以实体为中心构建血缘图，返回 Vue Flow nodes + edges"""
    from app.core.lineage_service import build_lineage_graph

    if entity_type not in ("component", "sync_task", "table"):
        raise HTTPException(400, f"不支持的实体类型: {entity_type}")

    eid = entity_id if entity_type == "table" else int(entity_id)
    return build_lineage_graph(db, entity_type, eid, depth=depth)


@router.post("/lineage/refresh")
def refresh_lineage_api(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """全量刷新血缘数据"""
    from app.core.lineage_service import refresh_lineage
    return refresh_lineage(db)
