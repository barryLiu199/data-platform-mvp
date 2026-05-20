"""Tests for app/api/transfer.py — 导入导出 API (TDD vertical slices)"""
import json
import io
from app.models.component import Component
from app.models.component_folder import ComponentFolder
from app.models.datasource import DataSource
from app.models.workflow import Workflow
from app.models.project import Project


# ─── Helpers ──────────────────────────────────────────────────────

def _make_component(db, *, id=1, name="test_sql", comp_type="sql", config=None, folder_id=None):
    """Helper: 创建一个 Component 并 flush"""
    comp = Component(
        id=id, name=name, type=comp_type,
        config_json=config or {"sql": "SELECT 1"},
        folder_id=folder_id, created_by=1,
    )
    db.add(comp)
    db.flush()
    return comp


def _make_datasource(db, *, id=1, name="ods_mysql", ds_type="mysql"):
    """Helper: 创建一个 DataSource"""
    ds = DataSource(
        id=id, name=name, type=ds_type,
        host="localhost", port=3306, database_name="test",
        username="root", password="secret",
    )
    db.add(ds)
    db.flush()
    return ds


def _make_workflow(db, *, id=1, name="test_wf", comp_ids=None):
    """Helper: 创建一个 Workflow，dag_json 引用给定的 component_ids"""
    nodes = []
    edges = []
    for i, cid in enumerate(comp_ids or []):
        nodes.append({"id": f"node_{i}", "component_id": cid, "name": f"step_{i}"})
        if i > 0:
            edges.append({"source": f"node_{i-1}", "target": f"node_{i}"})
    wf = Workflow(
        id=id, name=name,
        dag_json={"nodes": nodes, "edges": edges},
        created_by=1,
    )
    db.add(wf)
    db.flush()
    return wf


def _upload(client, data: dict, strategy="skip", datasource_mapping=None):
    """Helper: 模拟文件上传导入"""
    content = json.dumps(data).encode()
    files = {"file": ("test.json", io.BytesIO(content), "application/json")}
    data_fields = {}
    if datasource_mapping is not None:
        data_fields["datasource_mapping"] = json.dumps(datasource_mapping)
    return client.post(
        f"/api/transfer/import?strategy={strategy}",
        files=files,
        data=data_fields,
    )


def _preview_upload(client, data: dict):
    """Helper: 模拟预览上传"""
    content = json.dumps(data).encode()
    return client.post(
        "/api/transfer/import/preview",
        files={"file": ("test.json", io.BytesIO(content), "application/json")},
    )


# ─── Slice 1: 导出组件 — v2 格式 ─────────────────────────────────

def test_export_components_returns_v2_structure(client, db_session):
    """POST /export/components → v2 格式，含 format_version 和 datasources"""
    comp = _make_component(db_session)

    resp = client.post("/api/transfer/export/components", json={"ids": [comp.id]})
    assert resp.status_code == 200

    data = resp.json()
    assert data["format_version"] == "2.0"
    assert data["type"] == "component"
    assert "datasources" in data
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["name"] == "test_sql"
    assert item["type"] == "sql"
    assert "uuid" in item


def test_export_component_with_datasource_ref(client, db_session):
    """SQL 组件导出时 datasource_id 被替换为 ${ds:name} 引用"""
    ds = _make_datasource(db_session, id=5, name="ods_mysql")
    comp = _make_component(
        db_session, config={"datasource_id": 5, "sql": "SELECT 1", "timeout": 30},
    )

    resp = client.post("/api/transfer/export/components", json={"ids": [comp.id]})
    data = resp.json()

    item = data["items"][0]
    cfg = item["config_json"]
    assert "datasource_id" not in cfg
    assert cfg["datasource_ref"] == "${ds:ods_mysql}"
    assert cfg["sql"] == "SELECT 1"

    # datasources 清单
    assert "ods_mysql" in data["datasources"]
    assert data["datasources"]["ods_mysql"]["type"] == "mysql"


def test_export_datax_component_strips_raw_json(client, db_session):
    """DataX 组件导出时 rawJson/sync_task_id 被剥离，source_id/target_id 替换为 ref"""
    src = _make_datasource(db_session, id=3, name="src_mysql")
    tgt = _make_datasource(db_session, id=7, name="tgt_ck", ds_type="clickhouse")
    comp = _make_component(
        db_session, comp_type="datax",
        config={
            "source_id": 3, "target_id": 7,
            "sync_task_id": 12, "rawJson": '{"huge":"json with passwords"}',
        },
    )

    resp = client.post("/api/transfer/export/components", json={"ids": [comp.id]})
    cfg = resp.json()["items"][0]["config_json"]

    assert "source_id" not in cfg
    assert "target_id" not in cfg
    assert "rawJson" not in cfg
    assert "sync_task_id" not in cfg
    assert cfg["source_ref"] == "${ds:src_mysql}"
    assert cfg["target_ref"] == "${ds:tgt_ck}"


def test_export_component_with_folder_path(client, db_session):
    """导出的组件包含正确的 folder_path"""
    folder = ComponentFolder(id=1, name="SQL", type="sql", parent_id=None, depth=0)
    db_session.add(folder)
    sub = ComponentFolder(id=2, name="ADS", type="sql", parent_id=1, depth=1)
    db_session.add(sub)
    db_session.flush()

    comp = _make_component(db_session, folder_id=2)
    resp = client.post("/api/transfer/export/components", json={"ids": [comp.id]})
    item = resp.json()["items"][0]
    assert item["folder_path"] == "SQL/ADS"


def test_export_deterministic_output(client, db_session):
    """同一组件导出两次，JSON 输出一致（Git 友好）"""
    _make_component(db_session)

    resp1 = client.post("/api/transfer/export/components", json={"ids": [1]})
    resp2 = client.post("/api/transfer/export/components", json={"ids": [1]})

    # 去掉 exported_at（时间戳可能不同）
    d1 = resp1.json()
    d2 = resp2.json()
    d1.pop("exported_at", None)
    d2.pop("exported_at", None)
    assert d1 == d2


# ─── Slice 2: 导出组件 — 边界条件 ─────────────────────────────────

def test_export_nonexistent_component_returns_400(client, db_session):
    """传入不存在的 ID → 400"""
    resp = client.post("/api/transfer/export/components", json={"ids": [9999]})
    assert resp.status_code == 400


# ─── Slice 3: 导出工作流 — 含内联组件 + v2 ─────────────────────────

def test_export_workflow_v2_includes_datasources(client, db_session):
    """工作流导出 v2 格式，含 datasources 清单和参数化组件"""
    ds = _make_datasource(db_session, id=5, name="ods_mysql")
    comp = _make_component(
        db_session, id=10, name="step_comp",
        config={"datasource_id": 5, "sql": "SELECT 1"},
    )
    wf = _make_workflow(db_session, comp_ids=[10])

    resp = client.post("/api/transfer/export/workflows", json={"ids": [wf.id]})
    assert resp.status_code == 200

    data = resp.json()
    assert data["format_version"] == "2.0"
    assert "datasources" in data
    assert "ods_mysql" in data["datasources"]

    wf_item = data["items"][0]
    inline_comp = wf_item["components"][0]
    assert inline_comp["config_json"]["datasource_ref"] == "${ds:ods_mysql}"
    assert "datasource_id" not in inline_comp["config_json"]


def test_export_workflow_embeds_component_uuid_in_dag(client, db_session):
    """DAG nodes 中嵌入 component_uuid"""
    comp = _make_component(db_session, id=10, name="step_comp")
    wf = _make_workflow(db_session, comp_ids=[10])

    resp = client.post("/api/transfer/export/workflows", json={"ids": [wf.id]})
    dag = resp.json()["items"][0]["dag_json"]
    node = dag["nodes"][0]
    assert "component_uuid" in node
    assert node["component_uuid"]  # non-empty


def test_export_nonexistent_workflow_returns_400(client, db_session):
    """不存在的工作流 → 400"""
    resp = client.post("/api/transfer/export/workflows", json={"ids": [9999]})
    assert resp.status_code == 400


# ─── Slice 4: 导入组件 — v1 向后兼容 ─────────────────────────────

def test_import_v1_component_creates_new(client, db_session):
    """导入 v1 格式组件 → 正常创建（向后兼容）"""
    bundle = {
        "version": "1.0", "type": "component",
        "items": [{
            "uuid": "uuid-new", "name": "imported_comp", "type": "sql",
            "config_json": {"datasource_id": 5, "sql": "SELECT 2"}, "folder_path": "",
            "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle)
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1

    comp = db_session.query(Component).filter(Component.name == "imported_comp").first()
    assert comp is not None
    assert comp.config_json["datasource_id"] == 5


def test_import_component_skip_existing(client, db_session):
    """同名组件 + skip 策略 → skipped=1"""
    _make_component(db_session, name="dup_comp")

    bundle = {
        "version": "1.0", "type": "component",
        "items": [{
            "uuid": "uuid-dup", "name": "dup_comp", "type": "sql",
            "config_json": {"sql": "SELECT 99"}, "folder_path": "",
            "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle, strategy="skip")
    data = resp.json()
    assert data["skipped"] == 1
    assert data["created"] == 0


# ─── Slice 5: 导入组件 — overwrite / rename ──────────────────────

def test_import_component_overwrite_existing(client, db_session):
    """同名组件 + overwrite → updated=1"""
    _make_component(db_session, name="ow_comp", config={"sql": "OLD"})

    bundle = {
        "version": "1.0", "type": "component",
        "items": [{
            "uuid": "uuid-ow", "name": "ow_comp", "type": "sql",
            "config_json": {"sql": "NEW"}, "folder_path": "",
            "status": "draft", "version": 1, "description": "updated",
        }],
    }
    resp = _upload(client, bundle, strategy="overwrite")
    data = resp.json()
    assert data["updated"] == 1

    db_session.expire_all()
    comp = db_session.query(Component).filter(Component.name == "ow_comp").first()
    assert comp.config_json == {"sql": "NEW"}


def test_import_component_rename_existing(client, db_session):
    """同名组件 + rename → 新建 xxx_imported"""
    _make_component(db_session, name="rn_comp")

    bundle = {
        "version": "1.0", "type": "component",
        "items": [{
            "uuid": "uuid-rn", "name": "rn_comp", "type": "sql",
            "config_json": {"sql": "SELECT 1"}, "folder_path": "",
            "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle, strategy="rename")
    data = resp.json()
    assert data["created"] == 1

    renamed = db_session.query(Component).filter(Component.name == "rn_comp_imported").first()
    assert renamed is not None


# ─── Slice 6: v2 导入 — 数据源映射 ─────────────────────────────

def test_import_v2_component_with_datasource_mapping(client, db_session):
    """v2 格式导入：${ds:xxx} 占位符被正确解析为本地数据源 PK"""
    local_ds = _make_datasource(db_session, id=99, name="local_mysql")

    bundle = {
        "format_version": "2.0", "type": "component",
        "datasources": {"ods_mysql": {"type": "mysql", "description": ""}},
        "items": [{
            "uuid": "uuid-v2", "name": "v2_comp", "type": "sql",
            "config_json": {"datasource_ref": "${ds:ods_mysql}", "sql": "SELECT 1"},
            "folder_path": "", "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle, datasource_mapping={"ods_mysql": 99})
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1

    comp = db_session.query(Component).filter(Component.name == "v2_comp").first()
    assert comp is not None
    assert comp.config_json["datasource_id"] == 99
    assert "datasource_ref" not in comp.config_json


def test_import_v2_datax_with_datasource_mapping(client, db_session):
    """v2 DataX 导入：source_ref/target_ref 解析为 source_id/target_id"""
    src = _make_datasource(db_session, id=10, name="src_db")
    tgt = _make_datasource(db_session, id=20, name="tgt_db", ds_type="clickhouse")

    bundle = {
        "format_version": "2.0", "type": "component",
        "datasources": {
            "src_db": {"type": "mysql"},
            "tgt_db": {"type": "clickhouse"},
        },
        "items": [{
            "uuid": "uuid-dx", "name": "v2_datax", "type": "datax",
            "config_json": {"source_ref": "${ds:src_db}", "target_ref": "${ds:tgt_db}"},
            "folder_path": "", "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle, datasource_mapping={"src_db": 10, "tgt_db": 20})
    assert resp.status_code == 200

    comp = db_session.query(Component).filter(Component.name == "v2_datax").first()
    assert comp.config_json["source_id"] == 10
    assert comp.config_json["target_id"] == 20
    assert "source_ref" not in comp.config_json
    assert "target_ref" not in comp.config_json


def test_import_v2_validates_mapping_type_mismatch(client, db_session):
    """v2 导入时类型不匹配 → 400 错误"""
    pg_ds = _make_datasource(db_session, id=50, name="pg_db", ds_type="postgresql")

    bundle = {
        "format_version": "2.0", "type": "component",
        "datasources": {"ods_mysql": {"type": "mysql"}},
        "items": [{
            "uuid": "uuid-mm", "name": "mm_comp", "type": "sql",
            "config_json": {"datasource_ref": "${ds:ods_mysql}", "sql": "SELECT 1"},
            "folder_path": "", "status": "draft", "version": 1, "description": "",
        }],
    }
    # 把 mysql 数据源映射到 postgresql 数据源 → 应该报错
    resp = _upload(client, bundle, datasource_mapping={"ods_mysql": 50})
    assert resp.status_code == 400
    assert "类型不匹配" in resp.json()["detail"]


def test_import_v2_missing_mapping_returns_400(client, db_session):
    """v2 导入时缺少映射 → 400 错误"""
    bundle = {
        "format_version": "2.0", "type": "component",
        "datasources": {"ods_mysql": {"type": "mysql"}},
        "items": [{
            "uuid": "uuid-nm", "name": "nm_comp", "type": "sql",
            "config_json": {"datasource_ref": "${ds:ods_mysql}", "sql": "SELECT 1"},
            "folder_path": "", "status": "draft", "version": 1, "description": "",
        }],
    }
    # 提供空映射 → 应该报错
    resp = _upload(client, bundle, datasource_mapping={})
    assert resp.status_code == 400


# ─── Slice 7: 导入预览 ──────────────────────────────────────────

def test_preview_import_detects_existing(client, db_session):
    """预览端点正确标记 new / exists"""
    _make_component(db_session, name="existing_comp")

    bundle = {
        "format_version": "2.0", "type": "component",
        "datasources": {},
        "items": [
            {"uuid": "u1", "name": "existing_comp", "type": "sql",
             "config_json": {}, "folder_path": "", "status": "draft", "version": 1},
            {"uuid": "u2", "name": "brand_new_comp", "type": "sql",
             "config_json": {}, "folder_path": "", "status": "draft", "version": 1},
        ],
    }
    resp = _preview_upload(client, bundle)
    assert resp.status_code == 200

    data = resp.json()
    assert data["format_version"] == "2.0"
    items = data["items"]
    assert len(items) == 2

    existing = next(i for i in items if i["name"] == "existing_comp")
    assert existing["status"] == "exists"

    new = next(i for i in items if i["name"] == "brand_new_comp")
    assert new["status"] == "new"


def test_preview_workflow_import_with_datasources(client, db_session):
    """工作流预览返回 datasources 清单"""
    bundle = {
        "format_version": "2.0", "type": "workflow",
        "datasources": {"ods_mysql": {"type": "mysql"}},
        "items": [{
            "uuid": "wf-u1", "name": "test_wf", "type": "workflow",
            "dag_json": {"nodes": [], "edges": []},
            "components": [],
        }],
    }
    resp = _preview_upload(client, bundle)
    assert resp.status_code == 200
    data = resp.json()
    assert "ods_mysql" in data["datasources"]


# ─── Slice 8: 导入工作流 — DAG 组件 ID 重映射 ────────────────────

def test_import_workflow_remaps_dag_component_ids(client, db_session):
    """导出→导入工作流后，DAG 中 component_id 被重映射"""
    comp = _make_component(db_session, id=100, name="remap_comp")
    wf = _make_workflow(db_session, comp_ids=[100])

    export_resp = client.post("/api/transfer/export/workflows", json={"ids": [wf.id]})
    export_data = export_resp.json()

    # 清库模拟新环境
    db_session.query(Workflow).delete()
    db_session.query(Component).delete()
    db_session.flush()

    # 导入（v2 无数据源引用的情况）
    resp = _upload(client, export_data, strategy="skip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] >= 2

    new_wf = db_session.query(Workflow).filter(Workflow.name == "test_wf").first()
    assert new_wf is not None
    new_comp = db_session.query(Component).filter(Component.name == "remap_comp").first()
    assert new_comp is not None

    dag_node = new_wf.dag_json["nodes"][0]
    assert dag_node["component_id"] == new_comp.id


# ─── Slice 9: 错误处理 ──────────────────────────────────────────

def test_import_invalid_json_returns_400(client):
    """上传非 JSON 内容 → 400"""
    resp = client.post(
        "/api/transfer/import?strategy=skip",
        files={"file": ("bad.json", io.BytesIO(b"not json!!!"), "application/json")},
    )
    assert resp.status_code == 400


def test_import_unknown_type_returns_400(client):
    """type 不是 component/workflow → 400"""
    bundle = {"version": "1.0", "type": "unknown", "items": []}
    resp = _upload(client, bundle)
    assert resp.status_code == 400


# ─── Slice 10: 预览组件导出 (v2) ─────────────────────────────────

def test_preview_component_export_v2(client, db_session):
    """GET /export/components/{id}/preview 返回 v2 格式"""
    ds = _make_datasource(db_session, id=5, name="ods_mysql")
    comp = _make_component(
        db_session, id=50, name="preview_comp",
        config={"datasource_id": 5, "sql": "SELECT 1"},
    )

    resp = client.get(f"/api/transfer/export/components/{comp.id}/preview")
    assert resp.status_code == 200

    data = resp.json()
    assert data["format_version"] == "2.0"
    assert "datasources" in data
    assert data["items"][0]["config_json"]["datasource_ref"] == "${ds:ods_mysql}"


def test_preview_nonexistent_component_returns_404(client, db_session):
    """不存在的组件预览 → 404"""
    resp = client.get("/api/transfer/export/components/9999/preview")
    assert resp.status_code == 404
