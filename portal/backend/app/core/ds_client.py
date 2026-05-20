"""DolphinScheduler API 客户端单例"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DSClient:
    _instance: Optional["DSClient"] = None

    def __init__(self):
        self._base_url = settings.DS_API_URL
        self._user = settings.DS_ADMIN_USER
        self._password = settings.DS_ADMIN_PASSWORD
        self._session_id: Optional[str] = None
        self._project_code: Optional[int] = None
        self._client = httpx.AsyncClient(timeout=30.0)

    @classmethod
    def get_instance(cls) -> "DSClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _login(self) -> bool:
        try:
            resp = await self._client.post(
                f"{self._base_url}/login",
                data={"userName": self._user, "userPassword": self._password},
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("sessionId"):
                self._session_id = data["data"]["sessionId"]
                logger.info("DS login success")
                return True
            logger.error("DS login failed: %s", data.get("msg"))
        except Exception as e:
            logger.error("DS login error: %s", e)
        return False

    async def _ensure_session(self) -> bool:
        if self._session_id:
            return True
        return await self._login()

    async def _discover_project(self) -> Optional[int]:
        """发现 DS 默认项目 code"""
        if self._project_code:
            return self._project_code
        data = await self.get("/projects", params={"pageNo": 1, "pageSize": 10})
        if data and data.get("totalList"):
            self._project_code = data["totalList"][0]["code"]
            logger.info("DS project code: %s", self._project_code)
            return self._project_code
        return None

    @property
    async def project_code(self) -> Optional[int]:
        return await self._discover_project()

    async def _request(self, method: str, path: str, retry: bool = True, **kwargs) -> Optional[dict]:
        if not await self._ensure_session():
            return None
        url = f"{self._base_url}{path}"
        cookies = {"sessionId": self._session_id}
        try:
            resp = await self._client.request(method, url, cookies=cookies, **kwargs)
            # DS 有时返回 body 尾部带多余数据，用 json.loads 截取第一个完整 JSON
            import json as _json
            raw = resp.text
            logger.info("DS raw response %s %s: %s", method, path, raw[:500])
            try:
                result = _json.loads(raw)
            except _json.JSONDecodeError:
                # 尝试只解析到第一个完整的 } 结束
                decoder = _json.JSONDecoder()
                result, _ = decoder.raw_decode(raw)
            # 401 重认证
            if result.get("code") in (300, 190001) and retry:
                self._session_id = None
                if await self._login():
                    return await self._request(method, path, retry=False, **kwargs)
                return None
            if result.get("code") == 0:
                return result.get("data")
            logger.warning("DS API %s %s returned: %s", method, path, result.get("msg"))
            return result.get("data")
        except Exception as e:
            logger.error("DS API error %s %s: %s", method, path, e)
            return None

    async def get(self, path: str, params: dict = None) -> Optional[dict]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict = None, json_data: dict = None) -> Optional[dict]:
        return await self._request("POST", path, data=data, json=json_data)

    async def put(self, path: str, data: dict = None, json_data: dict = None) -> Optional[dict]:
        return await self._request("PUT", path, data=data, json=json_data)

    async def delete(self, path: str) -> Optional[dict]:
        return await self._request("DELETE", path)

    async def healthy(self) -> bool:
        """检查 DS 是否可用"""
        try:
            resp = await self._client.get(
                f"{self._base_url}/actuator/health", timeout=5.0
            )
            data = resp.json()
            return data.get("status") == "UP"
        except Exception:
            return False

    # ─────────────────────────────────────────────
    # 高阶操作 — Process Definition & Schedule (Phase 5/6)
    # ─────────────────────────────────────────────

    async def gen_task_codes(self, count: int) -> Optional[list]:
        """让 DS 生成一批唯一 task code"""
        pc = await self._discover_project()
        if not pc:
            return None
        data = await self.get(f"/projects/{pc}/task-definition/gen-task-codes",
                              params={"genNum": count})
        # 不同版本可能返回 list 或 {code:[...]}
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or data.get("taskCodes") or []
        return None

    async def save_process_definition(
        self, name: str, description: str,
        task_definition_json: str, task_relation_json: str, locations: str,
        execution_type: str = "PARALLEL",
        global_params: str = "[]",
    ) -> Optional[int]:
        """创建 DS Process Definition,返回 code"""
        pc = await self._discover_project()
        if not pc:
            return None
        data = await self.post(f"/projects/{pc}/process-definition", data={
            "name": name,
            "description": description,
            "taskDefinitionJson": task_definition_json,
            "taskRelationJson": task_relation_json,
            "locations": locations,
            "executionType": execution_type,
            "globalParams": global_params,
            "timeout": 0,
        })
        if isinstance(data, dict):
            return data.get("code")
        return None

    async def update_process_definition(
        self, code: int, name: str, description: str,
        task_definition_json: str, task_relation_json: str, locations: str,
        execution_type: str = "PARALLEL",
        global_params: str = "[]",
    ) -> bool:
        """更新 DS Process Definition (需先 release=OFFLINE)"""
        pc = await self._discover_project()
        if not pc:
            return False
        # DS 更新接口走 PUT,需要 code 路径
        data = await self.put(f"/projects/{pc}/process-definition/{code}", data={
            "name": name,
            "description": description,
            "taskDefinitionJson": task_definition_json,
            "taskRelationJson": task_relation_json,
            "locations": locations,
            "executionType": execution_type,
            "globalParams": global_params,
            "timeout": 0,
            "releaseState": "OFFLINE",
        })
        return data is not None

    async def release_process_definition(self, code: int, online: bool) -> bool:
        """上线/下线 Process Definition"""
        pc = await self._discover_project()
        if not pc:
            return False
        state = "ONLINE" if online else "OFFLINE"
        data = await self.post(f"/projects/{pc}/process-definition/{code}/release", data={
            "releaseState": state,
            "name": "",
        })
        return data is not None

    async def delete_process_definition(self, code: int) -> bool:
        """删除 Process Definition"""
        pc = await self._discover_project()
        if not pc:
            return False
        data = await self.delete(f"/projects/{pc}/process-definition/{code}")
        return data is not None

    async def find_schedule_by_pd_code(self, pd_code: int) -> Optional[dict]:
        """根据 process-definition code 查找对应的 schedule"""
        pc = await self._discover_project()
        if not pc:
            return None
        data = await self.get(f"/projects/{pc}/schedules", params={
            "pageNo": 1, "pageSize": 10,
            "processDefinitionCode": pd_code,
        })
        items = (data or {}).get("totalList", [])
        return items[0] if items else None

    async def create_schedule(
        self, pd_code: int, cron: str,
        failure_strategy: str = "CONTINUE",
        warning_type: str = "NONE",
        warning_group_id: int = 0,
    ) -> Optional[int]:
        """为 process definition 创建 schedule,返回 schedule id"""
        pc = await self._discover_project()
        if not pc:
            return None
        # DS 的 schedule 字段较多,使用合理默认值
        schedule_payload = {
            "startTime": "2020-01-01 00:00:00",
            "endTime": "2099-12-31 23:59:59",
            "crontab": cron,
            "timezoneId": "Asia/Shanghai",
        }
        import json as _json
        data = await self.post(f"/projects/{pc}/schedules", data={
            "processDefinitionCode": pd_code,
            "schedule": _json.dumps(schedule_payload),
            "failureStrategy": failure_strategy,
            "warningType": warning_type,
            "warningGroupId": warning_group_id,
            "workerGroup": "default",
            "tenantCode": "default",
            "environmentCode": -1,
            "processInstancePriority": "MEDIUM",
        })
        if isinstance(data, dict):
            return data.get("id")
        return None

    async def update_schedule(
        self, schedule_id: int, cron: str,
        failure_strategy: str = "CONTINUE",
        warning_type: str = "NONE",
        warning_group_id: int = 0,
    ) -> bool:
        pc = await self._discover_project()
        if not pc:
            return False
        import json as _json
        schedule_payload = {
            "startTime": "2020-01-01 00:00:00",
            "endTime": "2099-12-31 23:59:59",
            "crontab": cron,
            "timezoneId": "Asia/Shanghai",
        }
        data = await self.put(f"/projects/{pc}/schedules/{schedule_id}", data={
            "schedule": _json.dumps(schedule_payload),
            "failureStrategy": failure_strategy,
            "warningType": warning_type,
            "warningGroupId": warning_group_id,
            "workerGroup": "default",
            "tenantCode": "default",
            "environmentCode": -1,
            "processInstancePriority": "MEDIUM",
        })
        return data is not None

    async def schedule_online(self, schedule_id: int) -> bool:
        pc = await self._discover_project()
        if not pc:
            return False
        data = await self.post(f"/projects/{pc}/schedules/{schedule_id}/online")
        return data is not None

    async def schedule_offline(self, schedule_id: int) -> bool:
        pc = await self._discover_project()
        if not pc:
            return False
        data = await self.post(f"/projects/{pc}/schedules/{schedule_id}/offline")
        return data is not None

    async def delete_schedule(self, schedule_id: int) -> bool:
        pc = await self._discover_project()
        if not pc:
            return False
        data = await self.delete(f"/projects/{pc}/schedules/{schedule_id}")
        return data is not None

    async def start_process_instance(self, pd_code: int, start_params: str = "") -> Optional[dict]:
        """手动启动一次工作流实例"""
        pc = await self._discover_project()
        if not pc:
            return None
        return await self.post(f"/projects/{pc}/executors/start-process-instance", data={
            "processDefinitionCode": pd_code,
            "failureStrategy": "CONTINUE",
            "warningType": "NONE",
            "scheduleTime": "",
            "startParams": start_params,
        })

    async def close(self):
        await self._client.aclose()


def get_ds_client() -> DSClient:
    return DSClient.get_instance()
