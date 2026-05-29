"""Tests for app/api/metadata_lineage.py — column lineage endpoints"""
import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.metadata_lineage import router
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.column_lineage import ColumnLineage, ColumnParseFailure


@pytest.fixture
def col_lineage_client(db_session, clean_tables):
    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "testadmin"
    fake_user.role = "admin"

    def _override_db():
        yield db_session

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user
    # require_permission 也走同一个 fake user
    from app.core import permissions as perm_mod
    app.dependency_overrides[require_permission("lineage:write")] = lambda: fake_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _add_lineage(db, **kw):
    row = ColumnLineage(
        source_table=kw.get("source_table", "ods_a"),
        source_column=kw.get("source_column", "id"),
        target_table=kw.get("target_table", "dw_a"),
        target_column=kw.get("target_column", "id"),
        entity_type=kw.get("entity_type", "sync_task"),
        entity_id=kw.get("entity_id", 1),
        entity_name=kw.get("entity_name", "t1"),
        transform_type=kw.get("transform_type", "identity"),
        parse_type=kw.get("parse_type", "datax"),
        parse_status="ok",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestColumnsList:
    def test_returns_distinct_columns(self, col_lineage_client, db_session, clean_tables):
        _add_lineage(db_session, target_table="dw_x", target_column="a")
        _add_lineage(db_session, target_table="dw_x", target_column="b")
        _add_lineage(db_session, source_table="dw_x", source_column="c",
                     target_table="ads", target_column="z")

        r = col_lineage_client.get("/api/metadata/lineage/columns?table=dw_x")
        assert r.status_code == 200
        body = r.json()
        assert body["table"] == "dw_x"
        assert sorted(body["columns_with_lineage"]) == ["a", "b", "c"]

    def test_empty_table(self, col_lineage_client, clean_tables):
        r = col_lineage_client.get("/api/metadata/lineage/columns?table=nonexistent")
        assert r.status_code == 200
        assert r.json()["columns_with_lineage"] == []


class TestColumnGraph:
    def test_basic_graph(self, col_lineage_client, db_session, clean_tables):
        _add_lineage(db_session, source_table="ods_a", source_column="id",
                     target_table="dw_a", target_column="id")
        _add_lineage(db_session, source_table="dw_a", source_column="id",
                     target_table="ads_a", target_column="id",
                     entity_type="component", entity_id=2)

        r = col_lineage_client.get("/api/metadata/lineage/columns/dw_a/id")
        assert r.status_code == 200
        body = r.json()
        assert body["stats"]["total_nodes"] == 3
        assert body["stats"]["total_edges"] == 2

    def test_invalid_direction(self, col_lineage_client, clean_tables):
        r = col_lineage_client.get("/api/metadata/lineage/columns/x/y?direction=sideways")
        assert r.status_code == 422


class TestParseFailures:
    def test_pagination(self, col_lineage_client, db_session, clean_tables):
        for i in range(5):
            db_session.add(ColumnParseFailure(
                entity_type="component", entity_id=i, entity_name=f"c{i}",
                sql_snippet="INSERT INTO ...", error_msg="mock error",
            ))
        db_session.commit()

        r = col_lineage_client.get("/api/metadata/lineage/parse-failures?page=1&page_size=3")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3


class TestManualLineage:
    def test_create_and_delete(self, col_lineage_client, db_session, clean_tables):
        r = col_lineage_client.post("/api/metadata/lineage/manual", json={
            "source_table": "ODS_X", "source_column": "Id",
            "target_table": "DW_X", "target_column": "uid",
            "transform_type": "identity",
        })
        assert r.status_code == 200
        row_id = r.json()["id"]

        # 已写入且 lower 化
        row = db_session.query(ColumnLineage).filter_by(id=row_id).one()
        assert row.source_table == "ods_x"
        assert row.target_column == "uid"
        assert row.entity_type == "manual"

        # 删除
        r = col_lineage_client.delete(f"/api/metadata/lineage/manual/{row_id}")
        assert r.status_code == 200
        assert db_session.query(ColumnLineage).filter_by(id=row_id).count() == 0

    def test_reject_invalid_transform_type(self, col_lineage_client, clean_tables):
        r = col_lineage_client.post("/api/metadata/lineage/manual", json={
            "source_table": "a", "source_column": "x",
            "target_table": "b", "target_column": "y",
            "transform_type": "weird",
        })
        assert r.status_code == 400

    def test_reject_empty_fields(self, col_lineage_client, clean_tables):
        r = col_lineage_client.post("/api/metadata/lineage/manual", json={
            "source_table": "", "source_column": "x",
            "target_table": "b", "target_column": "y",
        })
        assert r.status_code == 400

    def test_delete_only_manual(self, col_lineage_client, db_session, clean_tables):
        # 非 manual 条目不可被这个端点删除
        row = _add_lineage(db_session, entity_type="sync_task")
        r = col_lineage_client.delete(f"/api/metadata/lineage/manual/{row.id}")
        assert r.status_code == 404


class TestRefreshColumnLineage:
    def test_endpoint_returns_stats(self, col_lineage_client, clean_tables):
        r = col_lineage_client.post("/api/metadata/lineage/refresh-columns")
        assert r.status_code == 200
        body = r.json()
        assert "sync_task" in body
        assert "component_sql" in body
        assert "component_datax" in body
        assert "manual_kept" in body
