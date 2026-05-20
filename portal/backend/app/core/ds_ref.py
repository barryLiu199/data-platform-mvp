"""数据源引用的参数化 (导出) 与解析 (导入) 核心逻辑。

导出方向: datasource_id → ${ds:数据源名}
导入方向: ${ds:数据源名} → 本地 datasource_id
"""
import copy
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.datasource import DataSource

logger = logging.getLogger(__name__)

_REF_PATTERN = re.compile(r"^\$\{ds:(.+)\}$")


# ─── 导出方向 ──────────────────────────────────────────────────────

def collect_datasource_manifest(
    db: Session,
    components: list,
) -> tuple[dict, dict[int, str]]:
    """扫描组件列表，收集所有数据源引用。

    Returns:
        (manifest, pk_to_name_map)
        manifest: {"ods_mysql": {"type": "mysql", "description": "..."}, ...}
        pk_to_name_map: {5: "ods_mysql", 7: "dw_clickhouse", ...}
    """
    ds_ids: set[int] = set()
    for comp in components:
        cfg = comp.config_json or {} if hasattr(comp, "config_json") else (comp.get("config_json") or {})
        comp_type = comp.type if hasattr(comp, "type") else comp.get("type", "")

        if comp_type == "sql":
            ds_id = cfg.get("datasource_id")
            if ds_id:
                ds_ids.add(int(ds_id))
        elif comp_type == "datax":
            for key in ("source_id", "target_id"):
                ds_id = cfg.get(key)
                if ds_id:
                    ds_ids.add(int(ds_id))

    if not ds_ids:
        return {}, {}

    rows = db.query(DataSource).filter(DataSource.id.in_(ds_ids)).all()
    manifest: dict = {}
    pk_to_name: dict[int, str] = {}

    # 处理同名数据源的歧义
    name_count: dict[str, int] = {}
    for ds in rows:
        base = ds.name
        count = name_count.get(base, 0)
        if count > 0:
            logical_name = f"{base}_{count + 1}"
        else:
            logical_name = base
        name_count[base] = count + 1

        manifest[logical_name] = {
            "type": ds.type,
            "description": ds.description or "",
        }
        pk_to_name[ds.id] = logical_name

    return manifest, pk_to_name


def parameterize_config(
    config_json: dict,
    comp_type: str,
    ds_name_map: dict[int, str],
) -> dict:
    """导出方向: 将 config_json 中的数据源 PK 替换为 ${ds:name} 占位符。

    - SQL: datasource_id → datasource_ref
    - DataX: source_id/target_id → source_ref/target_ref, 剥离 rawJson/sync_task_id
    """
    cfg = copy.deepcopy(config_json)

    if comp_type == "sql":
        ds_id = cfg.pop("datasource_id", None)
        if ds_id and int(ds_id) in ds_name_map:
            cfg["datasource_ref"] = f"${{ds:{ds_name_map[int(ds_id)]}}}"

    elif comp_type == "datax":
        src_id = cfg.pop("source_id", None)
        tgt_id = cfg.pop("target_id", None)
        cfg.pop("rawJson", None)
        cfg.pop("sync_task_id", None)

        if src_id and int(src_id) in ds_name_map:
            cfg["source_ref"] = f"${{ds:{ds_name_map[int(src_id)]}}}"
        if tgt_id and int(tgt_id) in ds_name_map:
            cfg["target_ref"] = f"${{ds:{ds_name_map[int(tgt_id)]}}}"

    return cfg


# ─── 导入方向 ──────────────────────────────────────────────────────

def _extract_ref_name(ref_value: str) -> Optional[str]:
    """从 ${ds:xxx} 中提取 xxx。"""
    m = _REF_PATTERN.match(ref_value)
    return m.group(1) if m else None


def resolve_config(
    config_json: dict,
    comp_type: str,
    ds_mapping: dict[str, int],
) -> dict:
    """导入方向: 将 ${ds:name} 占位符替换为本地数据源 PK。

    - SQL: datasource_ref → datasource_id
    - DataX: source_ref/target_ref → source_id/target_id
    """
    cfg = copy.deepcopy(config_json)

    if comp_type == "sql":
        ref = cfg.pop("datasource_ref", None)
        if ref:
            name = _extract_ref_name(ref)
            if name and name in ds_mapping:
                cfg["datasource_id"] = ds_mapping[name]
            else:
                raise ValueError(f"数据源引用 '{ref}' 未在映射中找到")

    elif comp_type == "datax":
        src_ref = cfg.pop("source_ref", None)
        tgt_ref = cfg.pop("target_ref", None)

        if src_ref:
            name = _extract_ref_name(src_ref)
            if name and name in ds_mapping:
                cfg["source_id"] = ds_mapping[name]
            else:
                raise ValueError(f"数据源引用 '{src_ref}' 未在映射中找到")

        if tgt_ref:
            name = _extract_ref_name(tgt_ref)
            if name and name in ds_mapping:
                cfg["target_id"] = ds_mapping[name]
            else:
                raise ValueError(f"数据源引用 '{tgt_ref}' 未在映射中找到")

    return cfg


def validate_mapping(
    db: Session,
    manifest: dict,
    mapping: dict[str, int],
) -> list[str]:
    """校验数据源映射的完整性和类型匹配。

    Returns:
        错误消息列表（空列表表示通过）
    """
    errors: list[str] = []

    # 检查所有 manifest 条目都有映射
    for ds_name, info in manifest.items():
        if ds_name not in mapping:
            errors.append(f"缺少数据源 '{ds_name}' 的映射")
            continue

        local_id = mapping[ds_name]
        local_ds = db.query(DataSource).filter(DataSource.id == local_id).first()
        if not local_ds:
            errors.append(f"本地数据源 ID={local_id}（映射自 '{ds_name}'）不存在")
            continue

        expected_type = info.get("type", "")
        if expected_type and local_ds.type != expected_type:
            errors.append(
                f"数据源 '{ds_name}' 类型不匹配: 期望 {expected_type}, 实际 {local_ds.type}"
            )

    return errors
