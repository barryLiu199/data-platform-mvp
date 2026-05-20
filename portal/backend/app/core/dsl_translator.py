"""DSL Translator — 把 Portal Component / Workflow 翻译成 DolphinScheduler 原生 JSON

设计要点:
- Component (sql/python/shell/datax) → DS Task Definition
- Workflow (线性步骤) → DS Process Definition (taskDefinitionJson + taskRelationJson + locations)
- DataX 走 SHELL 节点 + heredoc 临时 JSON,不用 DS 原生 DataX 节点 (spec 冻结要求)
"""
import json
from typing import List, Dict, Any, Tuple, Optional


# DS 默认任务参数模板
DEFAULT_TASK_DEFAULTS = {
    "version": 0,
    "delayTime": "0",
    "flag": "YES",
    "isCache": "NO",
    "taskPriority": "MEDIUM",
    "workerGroup": "default",
    "environmentCode": -1,
    "failRetryTimes": "0",
    "failRetryInterval": "1",
    "timeoutFlag": "CLOSE",
    "timeoutNotifyStrategy": "",
    "timeout": 0,
    "cpuQuota": -1,
    "memoryMax": -1,
    "taskExecuteType": "BATCH",
}


def _datasource_type_for_ds(portal_type: str) -> str:
    """Portal 数据源 type → DS SQL 节点的 type 字段"""
    return (portal_type or "").upper() or "MYSQL"


def _build_datax_shell_script(config: Dict[str, Any]) -> str:
    """把 datax 组件 config 翻译成 SHELL 脚本 (heredoc 生成 JSON 后调 datax.py)

    config 期望字段:
      - rawJson: 完整 DataX job JSON 字符串 (优先)
      - 或 reader/writer/source_id/target_id: 高阶字段 (Phase 后期实现自动构造)
    """
    raw = config.get("rawJson")
    if not raw:
        # 兜底:把整个 config 序列化作为 job
        raw = json.dumps({"job": config}, ensure_ascii=False, indent=2)
    # 用 heredoc 写入临时文件,然后调用 datax.py
    # 注意: heredoc 用引号包裹 'EOF' 防止变量展开
    script = (
        "set -e\n"
        "JOB_FILE=/tmp/datax_job_$$_$(date +%s).json\n"
        "cat > \"$JOB_FILE\" <<'PORTAL_DATAX_EOF'\n"
        f"{raw}\n"
        "PORTAL_DATAX_EOF\n"
        "echo \"[Portal] datax job file: $JOB_FILE\"\n"
        "python /opt/datax/bin/datax.py \"$JOB_FILE\"\n"
        "rm -f \"$JOB_FILE\"\n"
    )
    return script


def _build_sql_shell_script(portal_ds: Any, sql_text: str) -> str:
    """把 SQL 组件翻译成 mysql CLI SHELL 脚本

    使用 base64 编码 SQL 内容，避免 DS 对 $ 符号的参数替换
    （DS 3.2.2 会把 $[*] 等 JSON PATH 表达式误认为参数表达式）。
    """
    import base64
    import shlex
    host = portal_ds.host or "localhost"
    port = portal_ds.port or 3306
    user = portal_ds.username or "root"
    password = portal_ds.password or ""
    database = portal_ds.database_name or ""
    # 前置 collation 设置
    full_sql = f"SET collation_connection = 'utf8mb4_0900_ai_ci';\n{sql_text}"
    b64 = base64.b64encode(full_sql.encode("utf-8")).decode("ascii")
    safe_password = shlex.quote(password)
    script = (
        "set -e\n"
        "SQL_FILE=/tmp/portal_sql_$$.sql\n"
        f"echo '{b64}' | base64 -d > \"$SQL_FILE\"\n"
        f"echo \"[Portal] executing SQL on {database}@{host}:{port}\"\n"
        f"mysql --default-character-set=utf8mb4 -h {shlex.quote(host)} -P {port} -u {shlex.quote(user)} -p{safe_password} {shlex.quote(database)} < \"$SQL_FILE\"\n"
        "echo \"[Portal] SQL executed successfully\"\n"
        "rm -f \"$SQL_FILE\"\n"
    )
    return script


def translate_component_to_task(
    component: Any,
    task_code: int,
    task_name: Optional[str] = None,
    datasource_lookup: Optional[Dict[int, Any]] = None,
    ds_datasource_id_map: Optional[Dict[int, int]] = None,
) -> Dict[str, Any]:
    """单个 Component → DS Task Definition JSON

    参数:
        component: SQLAlchemy Component 实例,需含 .type / .name / .config_json / .description
        task_code: DS 分配的任务编码
        task_name: 步骤名 (默认取 component.name)
        datasource_lookup: {id: DataSource} 用于 SQL 节点查 datasource 类型
    """
    cfg = component.config_json or {}
    ctype = component.type
    name = task_name or component.name
    base = {
        "code": task_code,
        "name": name,
        "description": component.description or "",
        **DEFAULT_TASK_DEFAULTS,
    }

    if ctype == "sql":
        ds_id = cfg.get("datasource_id")
        ds_type = "MYSQL"
        portal_ds = None
        if datasource_lookup and ds_id and ds_id in datasource_lookup:
            portal_ds = datasource_lookup[ds_id]
            ds_type = _datasource_type_for_ds(portal_ds.type)
        sql_text = cfg.get("sql", "")

        # 使用 SHELL 任务执行 SQL（避免 DS SQL 任务对 $ 等符号的参数替换）
        if portal_ds and ds_type == "MYSQL":
            # 通过 mysql CLI 执行，完全绕过 DS 的 SQL 参数解析
            shell_script = _build_sql_shell_script(portal_ds, sql_text)
            base["taskType"] = "SHELL"
            base["taskParams"] = {
                "rawScript": shell_script,
                "resourceList": [],
                "localParams": cfg.get("localParams", []),
            }
            if cfg.get("timeout"):
                base["timeoutFlag"] = "OPEN"
                base["timeout"] = int(cfg["timeout"]) // 60 or 1
        else:
            # 回退到 DS 原生 SQL 任务
            actual_ds_id = ds_id
            if ds_datasource_id_map and ds_id and ds_id in ds_datasource_id_map:
                actual_ds_id = ds_datasource_id_map[ds_id]
            sql_type = "0" if sql_text.strip().lower().startswith("select") else "1"
            base["taskType"] = "SQL"
            base["taskParams"] = {
                "type": ds_type,
                "datasource": actual_ds_id,
                "sql": sql_text,
                "sqlType": sql_type,
                "preStatements": cfg.get("preStatements", []),
                "postStatements": cfg.get("postStatements", []),
                "displayRows": 10,
                "localParams": cfg.get("localParams", []),
                "resourceList": [],
            }
            if cfg.get("timeout"):
                base["timeoutFlag"] = "OPEN"
                base["timeout"] = int(cfg["timeout"]) // 60 or 1  # DS timeout 单位是分钟

    elif ctype == "python":
        base["taskType"] = "PYTHON"
        base["taskParams"] = {
            "rawScript": cfg.get("script", ""),
            "resourceList": [],
            "localParams": cfg.get("localParams", []),
        }
        if cfg.get("timeout"):
            base["timeoutFlag"] = "OPEN"
            base["timeout"] = int(cfg["timeout"]) // 60 or 1

    elif ctype == "shell":
        base["taskType"] = "SHELL"
        base["taskParams"] = {
            "rawScript": cfg.get("script", ""),
            "resourceList": [],
            "localParams": cfg.get("localParams", []),
        }
        if cfg.get("timeout"):
            base["timeoutFlag"] = "OPEN"
            base["timeout"] = int(cfg["timeout"]) // 60 or 1

    elif ctype == "datax":
        # DataX 翻译成 SHELL + heredoc
        base["taskType"] = "SHELL"
        base["taskParams"] = {
            "rawScript": _build_datax_shell_script(cfg),
            "resourceList": [],
            "localParams": [],
        }
        # DataX 默认给更宽松的超时
        base["timeoutFlag"] = "OPEN"
        base["timeout"] = max(int(cfg.get("timeout", 1800)) // 60, 5)

    else:
        raise ValueError(f"不支持的组件类型: {ctype}")

    return base


def build_task_relations(task_codes: List[int]) -> List[Dict[str, Any]]:
    """线性流水线的 task relation (preTaskCode → postTaskCode)

    DS 约定:
      - 第一个任务用 preTaskCode=0 表示入口
      - 后续每个任务用前一个的 code 作为 preTaskCode
    """
    relations = []
    if not task_codes:
        return relations
    # 入口边
    relations.append({
        "preTaskCode": 0,
        "preTaskVersion": 0,
        "postTaskCode": task_codes[0],
        "postTaskVersion": 0,
        "name": "",
        "conditionType": "NONE",
        "conditionParams": {},
    })
    # 后续连接
    for i in range(1, len(task_codes)):
        relations.append({
            "preTaskCode": task_codes[i - 1],
            "preTaskVersion": 0,
            "postTaskCode": task_codes[i],
            "postTaskVersion": 0,
            "name": "",
            "conditionType": "NONE",
            "conditionParams": {},
        })
    return relations


def build_locations(task_codes: List[int]) -> List[Dict[str, Any]]:
    """线性流水线的节点坐标(DS DAG 图渲染用,横向排列)"""
    return [
        {"taskCode": code, "x": 200 + i * 220, "y": 200}
        for i, code in enumerate(task_codes)
    ]


def translate_workflow(
    workflow: Any,
    components_by_id: Dict[int, Any],
    task_codes: List[int],
    datasource_lookup: Optional[Dict[int, Any]] = None,
    ds_datasource_id_map: Optional[Dict[int, int]] = None,
) -> Dict[str, Any]:
    """Workflow → DS Process Definition save 所需的 4 个字段

    返回:
        {
            "name": ...,
            "description": ...,
            "taskDefinitionJson": "[...]",   # 已 JSON 序列化的字符串
            "taskRelationJson": "[...]",
            "locations": "[...]",
        }
    """
    steps = workflow.steps_json or []
    if len(steps) != len(task_codes):
        raise ValueError(f"steps 数 {len(steps)} 与 task_codes 数 {len(task_codes)} 不一致")

    task_defs = []
    for step, tcode in zip(steps, task_codes):
        cid = step.get("component_id")
        comp = components_by_id.get(cid)
        if not comp:
            raise ValueError(f"组件 {cid} 不存在")
        step_name = step.get("name") or comp.name
        td = translate_component_to_task(comp, tcode, task_name=step_name, datasource_lookup=datasource_lookup, ds_datasource_id_map=ds_datasource_id_map)
        task_defs.append(td)

    relations = build_task_relations(task_codes)
    locations = build_locations(task_codes)

    return {
        "name": workflow.name,
        "description": workflow.description or "",
        "taskDefinitionJson": json.dumps(task_defs, ensure_ascii=False),
        "taskRelationJson": json.dumps(relations, ensure_ascii=False),
        "locations": json.dumps(locations, ensure_ascii=False),
    }


# ============================================================
# DAG 模式翻译（支持并行分支和汇聚）
# ============================================================

def _topological_sort(nodes: List[Dict], edges: List[Dict]) -> List[str]:
    """Kahn 算法拓扑排序，同时检测环"""
    from collections import deque
    node_ids = {n["id"] for n in nodes}
    in_degree = {nid: 0 for nid in node_ids}
    adj = {nid: [] for nid in node_ids}
    for e in edges:
        if e["source"] in node_ids and e["target"] in node_ids:
            adj[e["source"]].append(e["target"])
            in_degree[e["target"]] += 1
    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    result = []
    while queue:
        nid = queue.popleft()
        result.append(nid)
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    if len(result) != len(node_ids):
        raise ValueError("DAG 中存在环，无法发布")
    return result


def build_task_relations_from_dag(
    edges: List[Dict],
    node_to_task_code: Dict[str, int],
    nodes: List[Dict],
) -> List[Dict[str, Any]]:
    """DAG 结构 → DS taskRelationJson"""
    node_ids = {n["id"] for n in nodes}
    targets_with_incoming = {e["target"] for e in edges if e["source"] in node_ids and e["target"] in node_ids}
    relations = []
    # Root nodes（入度为 0）
    for n in nodes:
        if n["id"] not in targets_with_incoming:
            relations.append({
                "preTaskCode": 0,
                "preTaskVersion": 0,
                "postTaskCode": node_to_task_code[n["id"]],
                "postTaskVersion": 0,
                "name": "",
                "conditionType": "NONE",
                "conditionParams": {},
            })
    # 普通边
    for e in edges:
        if e["source"] in node_ids and e["target"] in node_ids:
            relations.append({
                "preTaskCode": node_to_task_code[e["source"]],
                "preTaskVersion": 0,
                "postTaskCode": node_to_task_code[e["target"]],
                "postTaskVersion": 0,
                "name": "",
                "conditionType": "NONE",
                "conditionParams": {},
            })
    return relations


def build_locations_from_dag(
    nodes: List[Dict],
    node_to_task_code: Dict[str, int],
) -> List[Dict[str, Any]]:
    """直接使用前端保存的 position"""
    return [
        {"taskCode": node_to_task_code[n["id"]], "x": int(n["position"]["x"]), "y": int(n["position"]["y"])}
        for n in nodes
    ]


def translate_workflow_dag(
    workflow: Any,
    components_by_id: Dict[int, Any],
    task_codes: List[int],
    datasource_lookup: Optional[Dict[int, Any]] = None,
    ds_datasource_id_map: Optional[Dict[int, int]] = None,
) -> Dict[str, Any]:
    """DAG 版本: Workflow → DS Process Definition payload"""
    dag = workflow.dag_json
    nodes = dag["nodes"]
    edges = dag.get("edges", [])

    # 过滤 skip 节点及其关联边
    active_nodes = [n for n in nodes if not n.get("skip", False)]
    active_ids = {n["id"] for n in active_nodes}
    active_edges = [e for e in edges if e["source"] in active_ids and e["target"] in active_ids]

    # 环检测
    _topological_sort(active_nodes, active_edges)

    # 分配 task_code
    node_to_task_code = {}
    task_defs = []
    for i, node in enumerate(active_nodes):
        tcode = task_codes[i]
        node_to_task_code[node["id"]] = tcode
        comp = components_by_id.get(node["component_id"])
        if not comp:
            raise ValueError(f"组件 {node['component_id']} 不存在")
        td = translate_component_to_task(
            comp, tcode,
            task_name=node.get("name") or comp.name,
            datasource_lookup=datasource_lookup,
            ds_datasource_id_map=ds_datasource_id_map,
        )
        task_defs.append(td)

    relations = build_task_relations_from_dag(active_edges, node_to_task_code, active_nodes)
    locations = build_locations_from_dag(active_nodes, node_to_task_code)

    return {
        "name": workflow.name,
        "description": workflow.description or "",
        "taskDefinitionJson": json.dumps(task_defs, ensure_ascii=False),
        "taskRelationJson": json.dumps(relations, ensure_ascii=False),
        "locations": json.dumps(locations, ensure_ascii=False),
    }
