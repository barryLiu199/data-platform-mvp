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

from fastapi import BackgroundTasks
from pydantic import BaseModel

from app.core.database import get_db, SessionLocal
from app.core.permissions import require_permission
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """全量刷新血缘数据 — 表级同步执行；字段级以 BackgroundTask 异步触发，
    失败不影响表级返回。
    """
    from app.core.lineage_service import refresh_lineage
    table_stats = refresh_lineage(db)

    def _refresh_columns_bg():
        from app.core.column_lineage_service import refresh_column_lineage
        bg_db = SessionLocal()
        try:
            refresh_column_lineage(bg_db)
        except Exception:
            logger.exception("字段血缘后台刷新失败")
        finally:
            bg_db.close()

    background_tasks.add_task(_refresh_columns_bg)
    return {**table_stats, "column_refresh": "scheduled"}


# ========================= 字段级血缘 (column_lineage) =========================


class ManualColumnLineageIn(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    transform_type: str = "identity"
    transform_expr: str | None = None
    source_ds_id: int | None = None
    target_ds_id: int | None = None


@router.post("/lineage/refresh-columns")
def refresh_column_lineage_api(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("lineage:write")),
):
    """字段血缘全量刷新（同步）— 失败不影响表级血缘"""
    from app.core.column_lineage_service import refresh_column_lineage
    try:
        return refresh_column_lineage(db)
    except Exception as e:
        logger.exception("字段血缘刷新失败")
        raise HTTPException(500, f"字段血缘刷新失败: {e}")


@router.get("/lineage/columns")
def list_table_columns_with_lineage_hint(
    table: str = Query(..., description="表名"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """返回某张表中"哪些字段已有血缘"，前端用于在折叠态显示徽标
    返回: {table, columns_with_lineage: [col_name, ...]}
    """
    from app.models.column_lineage import ColumnLineage
    table_n = table.strip().lower()
    src = db.query(ColumnLineage.source_column).filter(
        ColumnLineage.source_table == table_n
    ).distinct().all()
    tgt = db.query(ColumnLineage.target_column).filter(
        ColumnLineage.target_table == table_n
    ).distinct().all()
    cols = sorted(set(r[0] for r in src) | set(r[0] for r in tgt))
    return {"table": table_n, "columns_with_lineage": cols}


@router.get("/lineage/columns/{table}/{column}")
def get_column_lineage_graph(
    table: str,
    column: str,
    direction: str = Query("both", regex="^(both|upstream|downstream)$"),
    depth: int = Query(3, ge=1, le=5),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """字段级 BFS 链路 — N 跳上下游字段图"""
    from app.core.column_lineage_service import build_column_lineage
    return build_column_lineage(db, table=table, column=column,
                                depth=depth, direction=direction)


@router.get("/lineage/parse-failures")
def list_column_parse_failures(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """字段血缘解析失败清单（分页）"""
    from app.models.column_lineage import ColumnParseFailure
    q = db.query(ColumnParseFailure).order_by(ColumnParseFailure.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_name": r.entity_name,
                "sql_snippet": r.sql_snippet,
                "error_msg": r.error_msg,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/lineage/manual")
def create_manual_column_lineage(
    payload: ManualColumnLineageIn,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("lineage:write")),
):
    """手工补登一条字段血缘（entity_type=manual，不参与全量清理）"""
    from app.models.column_lineage import ColumnLineage

    src_t = payload.source_table.strip().lower()
    src_c = payload.source_column.strip().lower()
    tgt_t = payload.target_table.strip().lower()
    tgt_c = payload.target_column.strip().lower()
    if not (src_t and src_c and tgt_t and tgt_c):
        raise HTTPException(400, "source/target table+column 均不能为空")
    if payload.transform_type not in ("identity", "expression", "aggregate", "join"):
        raise HTTPException(400, f"不支持的 transform_type: {payload.transform_type}")

    row = ColumnLineage(
        source_table=src_t, source_column=src_c,
        target_table=tgt_t, target_column=tgt_c,
        source_ds_id=payload.source_ds_id, target_ds_id=payload.target_ds_id,
        entity_type="manual", entity_id=None, entity_name="手工补登",
        transform_type=payload.transform_type,
        transform_expr=payload.transform_expr,
        parse_type="manual", parse_status="ok",
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.delete("/lineage/manual/{row_id}")
def delete_manual_column_lineage(
    row_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("lineage:write")),
):
    """删除一条手工补登字段血缘"""
    from app.models.column_lineage import ColumnLineage
    row = db.query(ColumnLineage).filter(
        ColumnLineage.id == row_id,
        ColumnLineage.entity_type == "manual",
    ).first()
    if not row:
        raise HTTPException(404, "记录不存在或不是手工补登条目")
    db.delete(row)
    db.commit()
    return {"ok": True}
