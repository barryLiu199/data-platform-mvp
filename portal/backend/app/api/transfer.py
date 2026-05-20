"""导入导出 API — 组件和工作流的 JSON 导入导出"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.core.ds_ref import (
    collect_datasource_manifest,
    parameterize_config,
    resolve_config,
    validate_mapping,
)
from app.models.component import Component
from app.models.component_folder import ComponentFolder
from app.models.datasource import DataSource
from app.models.workflow import Workflow
from app.models.project import Project
from app.models.user import SysUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transfer", tags=["导入导出"])

EXPORT_VERSION = "1.0"
EXPORT_FORMAT_VERSION = "2.0"


# ─── Request schemas ────────────────────────────────────────────────

class ExportIdsRequest(BaseModel):
    ids: List[int]


# ─── Helpers ────────────────────────────────────────────────────────

def _build_folder_path(db: Session, folder_id: Optional[int]) -> str:
    """Traverse ComponentFolder parent_id chain to build path like 'SQL/数仓层/ADS'."""
    if not folder_id:
        return ""
    parts: list[str] = []
    seen: set[int] = set()
    current_id = folder_id
    while current_id:
        if current_id in seen:
            logger.warning("Circular folder reference detected at folder_id=%s", current_id)
            break
        seen.add(current_id)
        folder = db.query(ComponentFolder).filter(ComponentFolder.id == current_id).first()
        if not folder:
            logger.warning("Folder id=%s not found while building path", current_id)
            break
        parts.append(folder.name)
        current_id = folder.parent_id
    parts.reverse()
    return "/".join(parts)


def _deterministic_uuid(name: str, comp_type: str) -> str:
    """Generate a deterministic UUID based on name + type for stable re-export."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"component:{name}:{comp_type}"))


def _serialize_component_for_export(
    db: Session, comp: Component, ds_name_map: Optional[dict[int, str]] = None,
) -> dict:
    """Serialize a Component to the portable export format.

    If ds_name_map is provided (v2), datasource PKs are replaced with ${ds:name} refs.
    """
    cfg = comp.config_json or {}
    if ds_name_map is not None:
        cfg = parameterize_config(cfg, comp.type, ds_name_map)

    return {
        "uuid": _deterministic_uuid(comp.name, comp.type),
        "name": comp.name,
        "type": comp.type,
        "config_json": cfg,
        "folder_path": _build_folder_path(db, comp.folder_id),
        "status": comp.status,
        "version": comp.version,
        "description": comp.description or "",
    }


def _collect_workflow_component_ids(wf: Workflow) -> list[int]:
    """Extract all component IDs referenced in dag_json and steps_json."""
    comp_ids: set[int] = set()
    # dag_json.nodes[].component_id
    dag = wf.dag_json or {}
    for node in dag.get("nodes", []):
        cid = node.get("component_id")
        if cid:
            comp_ids.add(int(cid))
    # steps_json[].component_id (legacy linear format)
    for step in (wf.steps_json or []):
        cid = step.get("component_id")
        if cid:
            comp_ids.add(int(cid))
    return sorted(comp_ids)


def _build_comp_id_to_uuid_map(db: Session, comp_ids: list[int]) -> dict[int, str]:
    """Build mapping from component integer ID to deterministic UUID for export."""
    result: dict[int, str] = {}
    if not comp_ids:
        return result
    comps = db.query(Component.id, Component.name, Component.type).filter(
        Component.id.in_(comp_ids)
    ).all()
    for c in comps:
        result[c.id] = _deterministic_uuid(c.name, c.type)
    return result


def _ensure_folder_path(db: Session, folder_path: str, folder_type: str) -> Optional[int]:
    """Create folders recursively from a path like 'SQL/数仓层/ADS', return leaf folder_id."""
    if not folder_path:
        return None
    parts = [p.strip() for p in folder_path.split("/") if p.strip()]
    if not parts:
        return None
    parent_id = None
    depth = 0
    for part in parts:
        existing = db.query(ComponentFolder).filter(
            ComponentFolder.name == part,
            ComponentFolder.type == folder_type,
            ComponentFolder.parent_id == parent_id if parent_id else ComponentFolder.parent_id.is_(None),
        ).first()
        if existing:
            parent_id = existing.id
        else:
            new_folder = ComponentFolder(
                name=part, type=folder_type, parent_id=parent_id, depth=depth,
            )
            db.add(new_folder)
            db.flush()
            parent_id = new_folder.id
        depth += 1
    return parent_id


def _resolve_item_config(
    item: dict, ds_mapping: Optional[dict[str, int]],
) -> dict:
    """Resolve datasource refs in item config_json (v2 format)."""
    cfg = item.get("config_json", {})
    if ds_mapping is None:
        return cfg
    comp_type = item.get("type", "sql")
    # 只处理含有 *_ref 字段的 v2 格式
    has_refs = any(k.endswith("_ref") for k in cfg if k in ("datasource_ref", "source_ref", "target_ref"))
    if not has_refs:
        return cfg
    return resolve_config(cfg, comp_type, ds_mapping)


def _import_components(
    db: Session, items: list[dict], strategy: str, user_id: int,
    ds_mapping: Optional[dict[str, int]] = None,
) -> dict:
    """Import component items. Returns {created, updated, skipped, errors, id_map}."""
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    id_map: dict[str, int] = {}  # uuid -> new component id

    for item in items:
        name = item.get("name", "")
        comp_type = item.get("type", "sql")
        item_uuid = item.get("uuid", "")
        try:
            # Resolve datasource refs for v2 format
            resolved_config = _resolve_item_config(item, ds_mapping)

            # Ensure folder exists
            folder_id = _ensure_folder_path(db, item.get("folder_path", ""), comp_type)

            existing = db.query(Component).filter(
                Component.name == name, Component.type == comp_type,
            ).first()

            if existing:
                if strategy == "skip":
                    skipped += 1
                    id_map[item_uuid] = existing.id
                    continue
                elif strategy == "overwrite":
                    existing.config_json = resolved_config
                    existing.description = item.get("description", "")
                    existing.version = item.get("version", 1)
                    existing.status = item.get("status", "draft")
                    existing.folder_id = folder_id
                    db.flush()
                    updated += 1
                    id_map[item_uuid] = existing.id
                    continue
                elif strategy == "rename":
                    name = f"{name}_imported"
                    # Check again after rename
                    existing2 = db.query(Component).filter(
                        Component.name == name, Component.type == comp_type,
                    ).first()
                    if existing2:
                        name = f"{name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            new_comp = Component(
                name=name,
                type=comp_type,
                config_json=resolved_config,
                description=item.get("description", ""),
                version=item.get("version", 1),
                status=item.get("status", "draft"),
                folder_id=folder_id,
                created_by=user_id,
            )
            db.add(new_comp)
            db.flush()
            created += 1
            id_map[item_uuid] = new_comp.id
        except Exception as e:
            logger.warning("Failed to import component '%s': %s", name, e)
            errors.append(f"组件 '{name}' 导入失败: {str(e)}")

    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors, "id_map": id_map}


# ─── Endpoints ──────────────────────────────────────────────────────

@router.post("/export/components")
def export_components(
    body: ExportIdsRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:read")),
):
    """导出组件为 JSON 文件（v2 参数化格式）"""
    comps = []
    for comp_id in body.ids:
        comp = db.query(Component).filter(Component.id == comp_id).first()
        if not comp:
            logger.warning("Export: component id=%s not found, skipping", comp_id)
            continue
        comps.append(comp)

    if not comps:
        raise HTTPException(status_code=400, detail="未找到可导出的组件")

    # 收集数据源清单
    manifest, ds_name_map = collect_datasource_manifest(db, comps)
    items = [_serialize_component_for_export(db, c, ds_name_map) for c in comps]

    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "format_version": EXPORT_FORMAT_VERSION,
        "type": "component",
        "exported_at": now_str,
        "datasources": manifest,
        "items": items,
        "metadata": {
            "source_project": "data-platform-mvp",
            "component_count": len(items),
        },
    }

    filename = f"components_export_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return JSONResponse(
        content=json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/workflows")
def export_workflows(
    body: ExportIdsRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("workflow:read")),
):
    """导出工作流为 JSON 文件（v2 参数化格式，含内联组件）"""
    items = []
    all_comp_count = 0

    # 先收集所有组件，统一构建数据源清单
    all_comps: list[Component] = []
    wf_list = []
    for wf_id in body.ids:
        wf = db.query(Workflow).filter(Workflow.id == wf_id).first()
        if not wf:
            logger.warning("Export: workflow id=%s not found, skipping", wf_id)
            continue
        wf_list.append(wf)
        comp_ids = _collect_workflow_component_ids(wf)
        for cid in comp_ids:
            comp = db.query(Component).filter(Component.id == cid).first()
            if comp:
                all_comps.append(comp)

    if not wf_list:
        raise HTTPException(status_code=400, detail="未找到可导出的工作流")

    # 统一数据源清单
    manifest, ds_name_map = collect_datasource_manifest(db, all_comps)

    # 构建参数
    all_params: dict = {}

    for wf in wf_list:
        comp_ids = _collect_workflow_component_ids(wf)
        comp_id_to_uuid = _build_comp_id_to_uuid_map(db, comp_ids)
        inline_components = []
        for cid in comp_ids:
            comp = db.query(Component).filter(Component.id == cid).first()
            if comp:
                inline_components.append(_serialize_component_for_export(db, comp, ds_name_map))
            else:
                logger.warning("Export: component id=%s referenced by workflow '%s' not found", cid, wf.name)
        all_comp_count += len(inline_components)

        # Embed component_uuid into dag_json nodes for stable remapping on import
        export_dag = dict(wf.dag_json or {})
        if "nodes" in export_dag:
            export_dag["nodes"] = []
            for node in (wf.dag_json or {}).get("nodes", []):
                node_copy = dict(node)
                cid = node_copy.get("component_id")
                if cid and int(cid) in comp_id_to_uuid:
                    node_copy["component_uuid"] = comp_id_to_uuid[int(cid)]
                export_dag["nodes"].append(node_copy)

        # Resolve project name
        project_name = ""
        if wf.project_id:
            proj = db.query(Project).filter(Project.id == wf.project_id).first()
            if proj:
                project_name = proj.name

        # Collect params
        for p in (wf.params_json or []):
            pname = p.get("prop") or p.get("name", "")
            if pname and pname not in all_params:
                all_params[pname] = {
                    "type": p.get("type", "VARCHAR"),
                    "default": p.get("value", ""),
                    "description": p.get("desc", ""),
                }

        wf_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"workflow:{wf.name}"))
        items.append({
            "uuid": wf_uuid,
            "name": wf.name,
            "description": wf.description or "",
            "dag_json": export_dag,
            "params_json": wf.params_json or [],
            "cron_expression": wf.cron_expression or "",
            "priority": wf.priority,
            "tags": wf.tags or [],
            "project_name": project_name,
            "components": inline_components,
        })

    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "format_version": EXPORT_FORMAT_VERSION,
        "type": "workflow",
        "exported_at": now_str,
        "datasources": manifest,
        "parameters": all_params,
        "items": items,
        "metadata": {
            "source_project": "data-platform-mvp",
            "workflow_count": len(items),
            "component_count": all_comp_count,
        },
    }

    filename = f"workflows_export_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return JSONResponse(
        content=json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_bundle(
    file: UploadFile = File(...),
    strategy: str = Query("skip", pattern="^(skip|overwrite|rename)$"),
    datasource_mapping: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:create")),
):
    """导入 JSON 文件（组件或工作流）。

    v2 格式支持 datasource_mapping 参数（JSON 字符串），将导出中的数据源名映射到本地 PK。
    """
    # Parse JSON
    try:
        raw = file.file.read()
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件过大，最大支持 10MB")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("Import: invalid JSON file: %s", e)
        raise HTTPException(status_code=400, detail="无效的 JSON 文件")

    bundle_type = data.get("type")
    if bundle_type not in ("component", "workflow"):
        raise HTTPException(status_code=400, detail=f"不支持的导入类型: {bundle_type}")

    # 检测格式版本
    format_version = data.get("format_version") or data.get("version", "1.0")
    is_v2 = format_version.startswith("2")

    # 解析数据源映射
    ds_mapping: Optional[dict[str, int]] = None
    if is_v2 and datasource_mapping:
        try:
            ds_mapping = json.loads(datasource_mapping)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="datasource_mapping 格式无效")

        # 校验映射
        manifest = data.get("datasources", {})
        if manifest:
            errors = validate_mapping(db, manifest, ds_mapping)
            if errors:
                raise HTTPException(status_code=400, detail=f"数据源映射校验失败: {'; '.join(errors)}")

    user_id = current_user.id

    if bundle_type == "component":
        result = _import_components(db, data.get("items", []), strategy, user_id, ds_mapping)
        db.commit()
        return {
            "created": result["created"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "errors": result["errors"],
        }

    # ─── workflow import ────────────────────────────────────────
    total_created = 0
    total_updated = 0
    total_skipped = 0
    all_errors: list[str] = []

    for wf_item in data.get("items", []):
        # 1. Import inline components first
        inline_comps = wf_item.get("components", [])
        comp_result = _import_components(db, inline_comps, strategy, user_id, ds_mapping)
        total_created += comp_result["created"]
        total_updated += comp_result["updated"]
        total_skipped += comp_result["skipped"]
        all_errors.extend(comp_result["errors"])
        id_map = comp_result["id_map"]  # uuid -> new_id

        # 2. Remap component IDs in dag_json using component_uuid
        dag = wf_item.get("dag_json", {})
        if dag and "nodes" in dag:
            for node in dag["nodes"]:
                comp_uuid = node.get("component_uuid")
                if comp_uuid and comp_uuid in id_map:
                    node["component_id"] = id_map[comp_uuid]
                elif not comp_uuid:
                    # Fallback for old exports without component_uuid: match by name
                    node_name = node.get("name", "")
                    for ic in inline_comps:
                        if ic.get("name") == node_name:
                            ic_uuid = ic.get("uuid", "")
                            if ic_uuid in id_map:
                                node["component_id"] = id_map[ic_uuid]
                                break

        # 3. Look up or create project
        project_id = None
        project_name = wf_item.get("project_name", "")
        if project_name:
            proj = db.query(Project).filter(Project.name == project_name).first()
            if proj:
                project_id = proj.id
            else:
                try:
                    new_proj = Project(
                        name=project_name,
                        code=project_name.lower().replace(" ", "_"),
                        description="由导入自动创建",
                    )
                    db.add(new_proj)
                    db.flush()
                    project_id = new_proj.id
                except Exception as e:
                    logger.warning("Failed to create project '%s': %s", project_name, e)

        # 4. Create or handle existing workflow
        wf_name = wf_item.get("name", "")
        try:
            existing_wf = db.query(Workflow).filter(Workflow.name == wf_name).first()
            if existing_wf:
                if strategy == "skip":
                    total_skipped += 1
                    continue
                elif strategy == "overwrite":
                    existing_wf.description = wf_item.get("description", "")
                    existing_wf.dag_json = dag
                    existing_wf.params_json = wf_item.get("params_json", [])
                    existing_wf.cron_expression = wf_item.get("cron_expression", "")
                    existing_wf.priority = wf_item.get("priority", 3)
                    existing_wf.tags = wf_item.get("tags", [])
                    existing_wf.project_id = project_id
                    db.flush()
                    total_updated += 1
                    continue
                elif strategy == "rename":
                    wf_name = f"{wf_name}_imported"

            new_wf = Workflow(
                name=wf_name,
                description=wf_item.get("description", ""),
                dag_json=dag,
                params_json=wf_item.get("params_json", []),
                cron_expression=wf_item.get("cron_expression", ""),
                priority=wf_item.get("priority", 3),
                tags=wf_item.get("tags", []),
                project_id=project_id,
                created_by=user_id,
            )
            db.add(new_wf)
            db.flush()
            total_created += 1
        except Exception as e:
            logger.warning("Failed to import workflow '%s': %s", wf_name, e)
            all_errors.append(f"工作流 '{wf_name}' 导入失败: {str(e)}")

    db.commit()
    return {
        "created": total_created,
        "updated": total_updated,
        "skipped": total_skipped,
        "errors": all_errors,
    }


@router.post("/import/preview")
def preview_import_bundle(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:read")),
):
    """预览导入文件 — 返回条目列表（含冲突检测）和数据源清单。"""
    try:
        raw = file.file.read()
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件过大，最大支持 10MB")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="无效的 JSON 文件")

    bundle_type = data.get("type")
    if bundle_type not in ("component", "workflow"):
        raise HTTPException(status_code=400, detail=f"不支持的导入类型: {bundle_type}")

    format_version = data.get("format_version") or data.get("version", "1.0")
    preview_items: list[dict] = []

    if bundle_type == "component":
        for item in data.get("items", []):
            name = item.get("name", "")
            comp_type = item.get("type", "sql")
            exists = db.query(Component).filter(
                Component.name == name, Component.type == comp_type,
            ).first() is not None
            preview_items.append({
                "name": name,
                "type": comp_type,
                "kind": "component",
                "uuid": item.get("uuid", ""),
                "status": "exists" if exists else "new",
            })
    else:
        for wf_item in data.get("items", []):
            # 工作流本身
            wf_name = wf_item.get("name", "")
            wf_exists = db.query(Workflow).filter(Workflow.name == wf_name).first() is not None
            preview_items.append({
                "name": wf_name,
                "type": "workflow",
                "kind": "workflow",
                "uuid": wf_item.get("uuid", ""),
                "status": "exists" if wf_exists else "new",
            })
            # 内联组件
            for item in wf_item.get("components", []):
                name = item.get("name", "")
                comp_type = item.get("type", "sql")
                exists = db.query(Component).filter(
                    Component.name == name, Component.type == comp_type,
                ).first() is not None
                preview_items.append({
                    "name": name,
                    "type": comp_type,
                    "kind": "component",
                    "uuid": item.get("uuid", ""),
                    "status": "exists" if exists else "new",
                })

    return {
        "format_version": format_version,
        "bundle_type": bundle_type,
        "items": preview_items,
        "datasources": data.get("datasources", {}),
        "parameters": data.get("parameters", {}),
    }


@router.get("/export/components/{comp_id}/preview")
def preview_component_export(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("component:read")),
):
    """预览单个组件的导出 JSON（v2 格式）"""
    comp = db.query(Component).filter(Component.id == comp_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="组件不存在")

    manifest, ds_name_map = collect_datasource_manifest(db, [comp])
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "type": "component",
        "exported_at": now_str,
        "datasources": manifest,
        "items": [_serialize_component_for_export(db, comp, ds_name_map)],
        "metadata": {
            "source_project": "data-platform-mvp",
            "component_count": 1,
        },
    }
