"""Tests for app/api/transfer.py — 导入导出 API (TDD vertical slices)"""
import json
import io
from app.models.component import Component
from app.models.component_folder import ComponentFolder
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


def _upload(client, data: dict, strategy="skip"):
    """Helper: 模拟文件上传导入"""
    content = json.dumps(data).encode()
    return client.post(
        f"/api/transfer/import?strategy={strategy}",
        files={"file": ("test.json", io.BytesIO(content), "application/json")},
    )


def _export_component_bundle(comp):
    """构造一个合法的组件导出 bundle"""
    return {
        "version": "1.0",
        "type": "component",
        "exported_at": "2026-01-01T00:00:00Z",
        "items": [
            {
                "uuid": f"uuid-{comp.name}",
                "name": comp.name,
                "type": comp.type,
                "config_json": comp.config_json,
                "folder_path": "",
                "status": "draft",
                "version": 1,
                "description": "",
            }
        ],
    }


# ─── Slice 1: 导出组件 — 正常路径 ─────────────────────────────────

def test_export_components_returns_valid_structure(client, db_session):
    """POST /export/components 传入有效 ID → 返回正确 JSON 结构"""
    comp = _make_component(db_session)

    resp = client.post("/api/transfer/export/components", json={"ids": [comp.id]})
    assert resp.status_code == 200

    data = resp.json()
    assert data["version"] == "1.0"
    assert data["type"] == "component"
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["name"] == "test_sql"
    assert item["type"] == "sql"
    assert item["config_json"] == {"sql": "SELECT 1"}
    assert "uuid" in item
    assert "folder_path" in item


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


# ─── Slice 2: 导出组件 — 边界条件 ─────────────────────────────────

def test_export_nonexistent_component_returns_400(client, db_session):
    """传入不存在的 ID → 400"""
    resp = client.post("/api/transfer/export/components", json={"ids": [9999]})
    assert resp.status_code == 400


# ─── Slice 3: 导出工作流 — 含内联组件 ─────────────────────────────

def test_export_workflow_includes_inline_components(client, db_session):
    """导出工作流时自动内联引用的组件"""
    comp = _make_component(db_session, id=10, name="step_comp")
    wf = _make_workflow(db_session, comp_ids=[10])

    resp = client.post("/api/transfer/export/workflows", json={"ids": [wf.id]})
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "workflow"
    wf_item = data["items"][0]
    assert wf_item["name"] == "test_wf"
    assert len(wf_item["components"]) == 1
    assert wf_item["components"][0]["name"] == "step_comp"


def test_export_workflow_embeds_component_uuid_in_dag(client, db_session):
    """DAG nodes 中嵌入 component_uuid 用于导入重映射"""
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


# ─── Slice 4: 导入组件 — skip 策略 ────────────────────────────────

def test_import_component_creates_new(client, db_session):
    """导入新组件 → created=1"""
    bundle = {
        "version": "1.0", "type": "component",
        "items": [{
            "uuid": "uuid-new", "name": "imported_comp", "type": "sql",
            "config_json": {"sql": "SELECT 2"}, "folder_path": "",
            "status": "draft", "version": 1, "description": "",
        }],
    }
    resp = _upload(client, bundle)
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert data["skipped"] == 0

    # 验证组件确实存在
    comp = db_session.query(Component).filter(Component.name == "imported_comp").first()
    assert comp is not None
    assert comp.config_json == {"sql": "SELECT 2"}


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


# ─── Slice 5: 导入组件 — overwrite 策略 ──────────────────────────

def test_import_component_overwrite_existing(client, db_session):
    """同名组件 + overwrite → updated=1, config 已更新"""
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
    assert comp.description == "updated"


# ─── Slice 6: 导入组件 — rename 策略 ─────────────────────────────

def test_import_component_rename_existing(client, db_session):
    """同名组件 + rename → 新建名为 xxx_imported 的组件"""
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


# ─── Slice 7: 导入工作流 — DAG 组件 ID 重映射 ────────────────────

def test_import_workflow_remaps_dag_component_ids(client, db_session):
    """导出→导入工作流后，DAG 中 component_id 被重映射为新创建的组件 ID"""
    # 先创建组件和工作流，导出
    comp = _make_component(db_session, id=100, name="remap_comp")
    wf = _make_workflow(db_session, comp_ids=[100])

    export_resp = client.post("/api/transfer/export/workflows", json={"ids": [wf.id]})
    export_data = export_resp.json()

    # 清库，模拟导入到新环境
    db_session.query(Workflow).delete()
    db_session.query(Component).delete()
    db_session.flush()

    # 导入
    resp = _upload(client, export_data, strategy="skip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] >= 2  # 至少 1 组件 + 1 工作流

    # 验证新工作流的 DAG component_id 指向新创建的组件
    new_wf = db_session.query(Workflow).filter(Workflow.name == "test_wf").first()
    assert new_wf is not None
    new_comp = db_session.query(Component).filter(Component.name == "remap_comp").first()
    assert new_comp is not None

    dag_node = new_wf.dag_json["nodes"][0]
    assert dag_node["component_id"] == new_comp.id


# ─── Slice 8: 导入 — 错误处理 ────────────────────────────────────

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


# ─── Slice 9: 预览组件导出 ───────────────────────────────────────

def test_preview_component_export(client, db_session):
    """GET /export/components/{id}/preview 返回正确结构"""
    comp = _make_component(db_session, id=50, name="preview_comp")

    resp = client.get(f"/api/transfer/export/components/{comp.id}/preview")
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "component"
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "preview_comp"


def test_preview_nonexistent_component_returns_404(client, db_session):
    """不存在的组件预览 → 404"""
    resp = client.get("/api/transfer/export/components/9999/preview")
    assert resp.status_code == 404
