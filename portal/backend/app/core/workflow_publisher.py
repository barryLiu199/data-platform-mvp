"""
WorkflowPublisher — 负责工作流与 DolphinScheduler 之间的同步操作。

职责：
  - publish:      翻译 Portal 工作流 → DS process-definition 并上线
  - unpublish:    下线 DS 调度 + process-definition
  - cleanup:      删除 DS 调度 + process-definition（尽量，失败仅记日志）
  - schedule_off: 下线 DS 调度
"""

import json
import logging
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.ds_client import DSClient
from app.core.dsl_translator import translate_workflow, translate_workflow_dag
from app.models.component import Component
from app.models.datasource import DataSource
from app.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowPublisher:
    """封装 Portal 工作流 ↔ DolphinScheduler 的全部交互逻辑。"""

    def __init__(self, db: Session, ds_client: DSClient):
        self.db = db
        self.ds = ds_client

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def publish(self, workflow: Workflow) -> Tuple[int, Optional[int]]:
        """把 workflow 翻译并同步到 DS（支持 DAG 和线性两种模式），返回 (pd_code, schedule_id)。"""
        active_nodes, comp_ids, node_count = self._resolve_nodes(workflow)
        comp_map = self._load_components(comp_ids)
        self._inject_datax_raw_json(comp_map)

        datasource_map = self._load_datasources(comp_map)
        ds_datasource_id_map = await self._ensure_datasources(datasource_map)

        task_codes = await self._gen_task_codes(node_count)
        payload = self._translate(workflow, comp_map, task_codes, datasource_map, ds_datasource_id_map)
        global_params = self._build_global_params(workflow)

        pd_code = await self._save_or_update(workflow, payload, global_params)
        schedule_id = await self._sync_schedule(workflow, pd_code)
        return pd_code, schedule_id

    async def unpublish(self, workflow: Workflow) -> None:
        """下线 DS 调度 + process definition（容忍失败）。"""
        if workflow.ds_schedule_id:
            try:
                await self.ds.schedule_offline(workflow.ds_schedule_id)
            except Exception as e:
                logger.warning("DS schedule offline failed for workflow %s: %s", workflow.id, e)
        if workflow.ds_process_code:
            try:
                await self.ds.release_process_definition(workflow.ds_process_code, online=False)
            except Exception as e:
                logger.warning("DS process offline failed for workflow %s: %s", workflow.id, e)

    async def cleanup(self, workflow: Workflow) -> None:
        """删除 DS 调度 + process definition（尽量，失败仅记日志继续删 Portal 记录）。"""
        if workflow.ds_schedule_id:
            try:
                await self.ds.schedule_offline(workflow.ds_schedule_id)
                await self.ds.delete_schedule(workflow.ds_schedule_id)
            except Exception as e:
                logger.warning("DS schedule cleanup failed for workflow %s: %s", workflow.id, e)
        if workflow.ds_process_code:
            try:
                await self.ds.release_process_definition(workflow.ds_process_code, online=False)
                await self.ds.delete_process_definition(workflow.ds_process_code)
            except Exception as e:
                logger.warning("DS process cleanup failed for workflow %s: %s", workflow.id, e)

    async def schedule_off(self, workflow: Workflow) -> None:
        """仅下线 DS 调度（容忍失败）。"""
        if workflow.ds_schedule_id:
            try:
                await self.ds.schedule_offline(workflow.ds_schedule_id)
            except Exception as e:
                logger.warning("DS schedule offline failed for workflow %s: %s", workflow.id, e)

    # ------------------------------------------------------------------
    # private helpers — publish 子步骤
    # ------------------------------------------------------------------

    def _resolve_nodes(self, workflow: Workflow) -> tuple:
        """确定节点数量和组件 ID 列表，返回 (active_nodes_or_None, comp_ids, node_count)。"""
        if workflow.dag_json and workflow.dag_json.get("nodes"):
            dag_nodes = workflow.dag_json["nodes"]
            active_nodes = [n for n in dag_nodes if not n.get("skip", False)]
            if not active_nodes:
                raise HTTPException(status_code=400, detail="DAG 中没有可执行的节点（全部被跳过）")
            comp_ids = [n["component_id"] for n in active_nodes]
            return active_nodes, comp_ids, len(active_nodes)
        else:
            steps = workflow.steps_json or []
            if not steps:
                raise HTTPException(status_code=400, detail="工作流为空")
            comp_ids = [s.get("component_id") for s in steps]
            return None, comp_ids, len(steps)

    def _load_components(self, comp_ids: list) -> Dict[int, Component]:
        comps = self.db.query(Component).filter(Component.id.in_(comp_ids)).all()
        return {c.id: c for c in comps}

    def _inject_datax_raw_json(self, comp_map: Dict[int, Component]) -> None:
        """DataX 组件: 如果 config_json 里有 sync_task_id 但没有 rawJson，动态生成。"""
        from app.core.datax_builder import build_for_sync_task
        from app.models.sync_task import SyncTask

        for c in comp_map.values():
            if c.type != "datax":
                continue
            cfg = c.config_json or {}
            if cfg.get("rawJson") or not cfg.get("sync_task_id"):
                continue
            task = self.db.query(SyncTask).filter(SyncTask.id == cfg["sync_task_id"]).first()
            if not task:
                continue
            src_ds = self.db.query(DataSource).filter(DataSource.id == task.source_id).first()
            tgt_ds = self.db.query(DataSource).filter(DataSource.id == task.target_id).first()
            if src_ds and tgt_ds:
                job = build_for_sync_task(task, src_ds, tgt_ds, mask_password=False)
                cfg["rawJson"] = json.dumps(job, ensure_ascii=False)
                c.config_json = cfg

    def _load_datasources(self, comp_map: Dict[int, Component]) -> Dict[int, DataSource]:
        ds_ids: set = set()
        for c in comp_map.values():
            cfg = c.config_json or {}
            if cfg.get("datasource_id"):
                ds_ids.add(cfg["datasource_id"])
        if not ds_ids:
            return {}
        dss = self.db.query(DataSource).filter(DataSource.id.in_(list(ds_ids))).all()
        return {d.id: d for d in dss}

    async def _ensure_datasources(self, datasource_map: Dict[int, DataSource]) -> Dict[int, int]:
        """自动注册 Portal 数据源到 DS，构建 Portal ID → DS ID 映射。"""
        ds_datasource_id_map: Dict[int, int] = {}
        for portal_id, portal_ds in datasource_map.items():
            ds_id = await self.ds.create_or_find_datasource(
                name=portal_ds.name,
                db_type=portal_ds.type or "mysql",
                host=portal_ds.host,
                port=portal_ds.port or 3306,
                database=portal_ds.database_name,
                username=portal_ds.username or "root",
                password=portal_ds.password or "",
            )
            if ds_id:
                ds_datasource_id_map[portal_id] = ds_id
                logger.info("Portal DS %s (id=%s) → DS datasource id=%s", portal_ds.name, portal_id, ds_id)
        return ds_datasource_id_map

    async def _gen_task_codes(self, node_count: int) -> list:
        task_codes = await self.ds.gen_task_codes(node_count)
        if not task_codes or len(task_codes) < node_count:
            raise HTTPException(status_code=502, detail="DS 生成 task code 失败")
        return [int(x) for x in task_codes[:node_count]]

    def _translate(
        self,
        workflow: Workflow,
        comp_map: dict,
        task_codes: list,
        datasource_map: dict,
        ds_datasource_id_map: dict,
    ) -> dict:
        if workflow.dag_json and workflow.dag_json.get("nodes"):
            return translate_workflow_dag(
                workflow, comp_map, task_codes,
                datasource_lookup=datasource_map,
                ds_datasource_id_map=ds_datasource_id_map,
            )
        return translate_workflow(
            workflow, comp_map, task_codes,
            datasource_lookup=datasource_map,
            ds_datasource_id_map=ds_datasource_id_map,
        )

    @staticmethod
    def _build_global_params(workflow: Workflow) -> str:
        raw_params = workflow.params_json or []
        ds_params = [
            {
                "prop": p.get("key", p.get("prop", "")),
                "direct": p.get("direct", "IN"),
                "type": p.get("type", "VARCHAR"),
                "value": p.get("value", ""),
            }
            for p in raw_params
        ]
        return json.dumps(ds_params, ensure_ascii=False)

    async def _save_or_update(self, workflow: Workflow, payload: dict, global_params: str) -> int:
        """已存在 ds_process_code → 更新；否则创建。创建/更新后上线。"""
        if workflow.ds_process_code:
            # 先 offline 才能更新
            await self.ds.release_process_definition(workflow.ds_process_code, online=False)
            ok = await self.ds.update_process_definition(
                workflow.ds_process_code,
                payload["name"], payload["description"],
                payload["taskDefinitionJson"], payload["taskRelationJson"], payload["locations"],
                global_params=global_params,
            )
            if not ok:
                raise HTTPException(status_code=502, detail="DS 更新 process-definition 失败")
            pd_code = workflow.ds_process_code
        else:
            pd_code = await self.ds.save_process_definition(
                payload["name"], payload["description"],
                payload["taskDefinitionJson"], payload["taskRelationJson"], payload["locations"],
                global_params=global_params,
            )
            if not pd_code:
                raise HTTPException(status_code=502, detail="DS 创建 process-definition 失败")

        # 上线 DS process definition
        ok = await self.ds.release_process_definition(pd_code, online=True)
        if not ok:
            raise HTTPException(status_code=502, detail="DS 上线 process-definition 失败")
        return pd_code

    async def _sync_schedule(self, workflow: Workflow, pd_code: int) -> Optional[int]:
        schedule_id = workflow.ds_schedule_id
        if workflow.cron_expression:
            if schedule_id:
                await self.ds.update_schedule(schedule_id, workflow.cron_expression)
            else:
                schedule_id = await self.ds.create_schedule(pd_code, workflow.cron_expression)
        return schedule_id
