"""Component Config — Pydantic Discriminated Union.

Centralizes all type-specific config_json interpretation in one place.
Callers use .code, .datasource_ids, etc. without knowing component type.

Usage:
    from app.core.component_config import parse_config
    config = parse_config(component.type, component.config_json)
    print(config.code)
    print(config.datasource_ids)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class SqlConfig(BaseModel):
    """SQL component config."""
    type: str = "sql"
    sql: str = ""
    datasource_id: Optional[int] = None
    timeout: Optional[int] = None

    @property
    def code(self) -> str:
        return self.sql

    @property
    def datasource_ids(self) -> List[int]:
        return [self.datasource_id] if self.datasource_id else []

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"sql": self.sql}
        if self.datasource_id:
            d["datasource_id"] = self.datasource_id
        if self.timeout:
            d["timeout"] = self.timeout
        return d


class PythonConfig(BaseModel):
    """Python component config."""
    type: str = "python"
    script: str = ""
    timeout: Optional[int] = None

    @property
    def code(self) -> str:
        return self.script

    @property
    def datasource_ids(self) -> List[int]:
        return []

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"script": self.script}
        if self.timeout:
            d["timeout"] = self.timeout
        return d


class ShellConfig(BaseModel):
    """Shell component config."""
    type: str = "shell"
    script: str = ""
    timeout: Optional[int] = None

    @property
    def code(self) -> str:
        return self.script

    @property
    def datasource_ids(self) -> List[int]:
        return []

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"script": self.script}
        if self.timeout:
            d["timeout"] = self.timeout
        return d


class DataxConfig(BaseModel):
    """DataX component config."""
    type: str = "datax"
    sync_task_id: Optional[int] = None
    rawJson: Optional[str] = None
    source_id: Optional[int] = None
    target_id: Optional[int] = None
    script: str = ""

    @property
    def code(self) -> str:
        return self.rawJson or self.script or ""

    @property
    def datasource_ids(self) -> List[int]:
        ids = []
        if self.source_id:
            ids.append(self.source_id)
        if self.target_id:
            ids.append(self.target_id)
        return ids

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.sync_task_id:
            d["sync_task_id"] = self.sync_task_id
        if self.rawJson:
            d["rawJson"] = self.rawJson
        if self.source_id:
            d["source_id"] = self.source_id
        if self.target_id:
            d["target_id"] = self.target_id
        if self.script:
            d["script"] = self.script
        return d


ComponentConfig = Union[SqlConfig, PythonConfig, ShellConfig, DataxConfig]

# Mapping from component type to config class
_CONFIG_CLASSES = {
    "sql": SqlConfig,
    "python": PythonConfig,
    "shell": ShellConfig,
    "datax": DataxConfig,
}


def parse_config(comp_type: str, config_json: Optional[Dict[str, Any]]) -> ComponentConfig:
    """Parse config_json into the appropriate typed config object.

    This is the single place that maps component type → config interpretation.
    All other code should use this function instead of manually branching on type.
    """
    cfg = config_json or {}
    comp_type = (comp_type or "sql").lower()
    cls = _CONFIG_CLASSES.get(comp_type, SqlConfig)

    if cls == SqlConfig:
        return SqlConfig(
            sql=cfg.get("sql", cfg.get("code", cfg.get("script", ""))),
            datasource_id=cfg.get("datasource_id"),
            timeout=cfg.get("timeout"),
        )
    elif cls == PythonConfig:
        return PythonConfig(
            script=cfg.get("script", cfg.get("code", cfg.get("sql", ""))),
            timeout=cfg.get("timeout"),
        )
    elif cls == ShellConfig:
        return ShellConfig(
            script=cfg.get("script", cfg.get("code", cfg.get("sql", ""))),
            timeout=cfg.get("timeout"),
        )
    elif cls == DataxConfig:
        return DataxConfig(
            sync_task_id=cfg.get("sync_task_id"),
            rawJson=cfg.get("rawJson"),
            source_id=cfg.get("source_id"),
            target_id=cfg.get("target_id"),
            script=cfg.get("script", cfg.get("code", "")),
        )
    return SqlConfig(sql=cfg.get("sql", ""))


def extract_code(comp_type: str, config_json: Optional[Dict[str, Any]]) -> str:
    """Convenience: extract the executable code from config_json."""
    return parse_config(comp_type, config_json).code


def extract_datasource_ids(comp_type: str, config_json: Optional[Dict[str, Any]]) -> List[int]:
    """Convenience: extract all datasource IDs referenced by this config."""
    return parse_config(comp_type, config_json).datasource_ids
