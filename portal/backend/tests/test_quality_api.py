"""Tests for app/api/quality.py — 规则 CRUD、执行、结果查询"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.quality import router
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import require_permission
from app.models.quality import QualityRule, QualityRuleTemplate, QualityCheckResult


@pytest.fixture
def quality_client(db_session, clean_tables):
    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "testadmin"
    fake_user.role = "admin"

    def _override_db():
        yield db_session

    with patch("app.api.quality.require_permission", return_value=lambda: fake_user):
        import importlib
        import app.api.quality as q_mod
        importlib.reload(q_mod)
        app = FastAPI()
        app.include_router(q_mod.router, prefix="/api")
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: fake_user
        yield TestClient(app)
        app.dependency_overrides.clear()


@pytest.fixture
def seed_templates(db_session):
    """Seed the 10 built-in templates"""
    import json
    templates = [
        {"code": "not_null", "name": "非空检查", "category": "completeness", "level": "field", "display_order": 1,
         "config_schema": json.dumps({"field": {"type": "string", "required": True}})},
        {"code": "uniqueness", "name": "唯一性检查", "category": "consistency", "level": "field", "display_order": 2,
         "config_schema": json.dumps({"fields": {"type": "array", "required": True}})},
        {"code": "null_rate", "name": "字段空值率", "category": "completeness", "level": "field", "display_order": 3,
         "config_schema": json.dumps({"field": {"type": "string"}, "threshold_pct": {"type": "number"}})},
        {"code": "value_range", "name": "值域范围", "category": "accuracy", "level": "field", "display_order": 4,
         "config_schema": json.dumps({"field": {"type": "string"}, "min_value": {"type": "number"}})},
        {"code": "regex_match", "name": "正则匹配", "category": "accuracy", "level": "field", "display_order": 5,
         "config_schema": json.dumps({"field": {"type": "string"}, "pattern": {"type": "string"}})},
        {"code": "row_count", "name": "行数波动", "category": "completeness", "level": "table", "display_order": 6,
         "config_schema": json.dumps({"threshold_pct": {"type": "number"}})},
        {"code": "timeliness", "name": "及时性", "category": "timeliness", "level": "table", "display_order": 7,
         "config_schema": json.dumps({"date_field": {"type": "string"}})},
        {"code": "dict_ref", "name": "字典引用", "category": "consistency", "level": "field", "display_order": 8,
         "config_schema": json.dumps({"field": {"type": "string"}, "dict_table": {"type": "string"}})},
        {"code": "custom_sql", "name": "自定义SQL", "category": "accuracy", "level": "any", "display_order": 9,
         "config_schema": json.dumps({"sql": {"type": "string"}, "operator": {"type": "string"}})},
        {"code": "cross_table_check", "name": "跨表核对", "category": "accuracy", "level": "table", "display_order": 10,
         "config_schema": json.dumps({"ds_id_a": {"type": "integer"}, "table_a": {"type": "string"}})},
    ]
    for t in templates:
        db_session.add(QualityRuleTemplate(**t))
    db_session.commit()


# ===== Template tests =====

class TestTemplates:
    def test_list_templates(self, quality_client, seed_templates):
        resp = quality_client.get("/api/quality/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 10
        codes = {t["code"] for t in data}
        assert "not_null" in codes
        assert "cross_table_check" in codes

    def test_templates_sorted(self, quality_client, seed_templates):
        resp = quality_client.get("/api/quality/templates")
        data = resp.json()
        orders = [t["display_order"] for t in data]
        assert orders == sorted(orders)


# ===== Rules CRUD =====

class TestRulesCRUD:
    def test_create_rule(self, quality_client, seed_templates):
        resp = quality_client.post("/api/quality/rules", json={
            "name": "订单非空",
            "template_code": "not_null",
            "datasource_id": 1,
            "table_name": "orders",
            "config": {"field": "order_id"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data

    def test_create_invalid_template(self, quality_client, seed_templates):
        resp = quality_client.post("/api/quality/rules", json={
            "name": "test",
            "template_code": "nonexistent",
            "config": {},
        })
        assert resp.status_code == 400

    def test_list_rules(self, quality_client, seed_templates, db_session):
        db_session.add(QualityRule(
            name="test1", template_code="not_null", config={"field": "x"},
            datasource_id=1, table_name="t1", created_by=1,
        ))
        db_session.add(QualityRule(
            name="test2", template_code="uniqueness", config={"fields": ["id"]},
            datasource_id=2, table_name="t2", created_by=1,
        ))
        db_session.commit()

        resp = quality_client.get("/api/quality/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_rules_filter_template(self, quality_client, seed_templates, db_session):
        db_session.add(QualityRule(name="r1", template_code="not_null", config={}, created_by=1))
        db_session.add(QualityRule(name="r2", template_code="uniqueness", config={}, created_by=1))
        db_session.commit()

        resp = quality_client.get("/api/quality/rules?template_code=not_null")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["template_code"] == "not_null"

    def test_get_rule_detail(self, quality_client, seed_templates, db_session):
        rule = QualityRule(
            name="detail_test", template_code="not_null",
            config={"field": "x"}, datasource_id=1, table_name="t", created_by=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.get(f"/api/quality/rules/{rule.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail_test"
        assert data["config"] == {"field": "x"}
        assert "recent_results" in data

    def test_get_rule_not_found(self, quality_client, seed_templates):
        resp = quality_client.get("/api/rules/9999")
        assert resp.status_code == 404

    def test_update_rule(self, quality_client, seed_templates, db_session):
        rule = QualityRule(name="old", template_code="not_null", config={}, created_by=1)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.put(f"/api/quality/rules/{rule.id}", json={"name": "new_name", "severity": "error"})
        assert resp.status_code == 200
        db_session.refresh(rule)
        assert rule.name == "new_name"
        assert rule.severity == "error"

    def test_delete_rule(self, quality_client, seed_templates, db_session):
        rule = QualityRule(name="to_del", template_code="not_null", config={}, created_by=1)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.delete(f"/api/quality/rules/{rule.id}")
        assert resp.status_code == 200
        assert db_session.query(QualityRule).get(rule.id) is None

    def test_toggle_rule(self, quality_client, seed_templates, db_session):
        rule = QualityRule(name="toggle", template_code="not_null", config={}, enabled=True, created_by=1)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.patch(f"/api/quality/rules/{rule.id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


# ===== Execution =====

class TestExecution:
    def test_execute_single(self, quality_client, seed_templates, db_session):
        rule = QualityRule(
            name="exec_test", template_code="not_null",
            config={"field": "x"}, datasource_id=1, table_name="t",
            enabled=True, created_by=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        with patch("app.api.quality.execute_rule") as mock_exec:
            resp = quality_client.post(f"/api/quality/rules/{rule.id}/execute")
            assert resp.status_code == 200
            assert "已提交" in resp.json()["message"]

    def test_execute_disabled_rule(self, quality_client, seed_templates, db_session):
        rule = QualityRule(
            name="disabled", template_code="not_null",
            config={}, enabled=False, created_by=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.post(f"/api/quality/rules/{rule.id}/execute")
        assert resp.status_code == 400

    def test_batch_execute(self, quality_client, seed_templates, db_session):
        for i in range(3):
            db_session.add(QualityRule(
                name=f"batch{i}", template_code="not_null",
                config={}, enabled=True, created_by=1,
            ))
        db_session.commit()

        with patch("app.api.quality.execute_rule"):
            resp = quality_client.post("/api/quality/rules/batch-execute", json={})
            assert resp.status_code == 200
            assert "3" in resp.json()["message"]

    def test_preview_sql(self, quality_client, seed_templates, db_session):
        rule = QualityRule(
            name="preview", template_code="not_null",
            config={"field": "amount"}, datasource_id=1, table_name="orders",
            created_by=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.post("/api/quality/rules/preview-sql", json={"rule_id": rule.id})
        assert resp.status_code == 200
        assert "amount IS NULL" in resp.json()["sql"]


# ===== Results =====

class TestResults:
    def test_list_results(self, quality_client, db_session):
        db_session.add(QualityCheckResult(
            rule_id=1, check_date=date.today(), status="pass",
            actual_value=0, triggered_by="manual",
        ))
        db_session.add(QualityCheckResult(
            rule_id=2, check_date=date.today(), status="fail",
            actual_value=5, triggered_by="workflow",
        ))
        db_session.commit()

        resp = quality_client.get("/api/quality/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_results_filter(self, quality_client, db_session):
        db_session.add(QualityCheckResult(
            rule_id=1, check_date=date.today(), status="pass",
            actual_value=0, triggered_by="manual",
        ))
        db_session.add(QualityCheckResult(
            rule_id=2, check_date=date.today(), status="fail",
            actual_value=5, triggered_by="manual",
        ))
        db_session.commit()

        resp = quality_client.get("/api/quality/results?status=fail")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "fail"

    def test_trend(self, quality_client, db_session):
        from datetime import timedelta
        for i in range(5):
            db_session.add(QualityCheckResult(
                rule_id=1, check_date=date.today() - timedelta(days=i),
                status="pass", actual_value=0, triggered_by="manual",
            ))
        db_session.commit()

        resp = quality_client.get("/api/quality/results/trend?rule_id=1&days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5


# ===== Stats =====

class TestStats:
    def test_stats(self, quality_client, seed_templates, db_session):
        db_session.add(QualityRule(name="s1", template_code="not_null", config={}, enabled=True, created_by=1))
        db_session.add(QualityRule(name="s2", template_code="not_null", config={}, enabled=False, created_by=1))
        db_session.add(QualityCheckResult(
            rule_id=1, check_date=date.today(), status="pass", actual_value=0, triggered_by="manual",
        ))
        db_session.add(QualityCheckResult(
            rule_id=2, check_date=date.today(), status="fail", actual_value=3, triggered_by="manual",
        ))
        db_session.commit()

        resp = quality_client.get("/api/quality/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rules"] == 2
        assert data["enabled_rules"] == 1
        assert data["today_pass"] == 1
        assert data["today_fail"] == 1


# ===== Metadata Quality =====

class TestMetadataQuality:
    def test_metadata_quality(self, quality_client, seed_templates, db_session):
        rule = QualityRule(
            name="meta_q", template_code="not_null", config={"field": "x"},
            datasource_id=5, table_name="my_table", created_by=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = quality_client.get("/api/quality/metadata/quality?datasource_id=5&table_name=my_table")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rule_name"] == "meta_q"
