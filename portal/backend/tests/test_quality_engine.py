"""Tests for app/core/quality_engine.py — SQL 生成 + 评估 + 跨表比较"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from app.core.quality_engine import (
    _gen_not_null, _gen_uniqueness, _gen_null_rate, _gen_value_range,
    _gen_regex_match, _gen_row_count, _gen_timeliness, _gen_dict_ref,
    _gen_custom_sql, _gen_cross_table_check,
    _evaluate, compare_datasets, execute_rule, preview_sql,
    GENERATORS,
)
from app.models.quality import QualityRule


def _make_rule(**kwargs):
    rule = MagicMock(spec=QualityRule)
    rule.id = kwargs.get("id", 1)
    rule.table_name = kwargs.get("table_name", "orders")
    rule.template_code = kwargs.get("template_code", "not_null")
    rule.datasource_id = kwargs.get("datasource_id", 1)
    rule.config = kwargs.get("config", {})
    rule.enabled = kwargs.get("enabled", True)
    return rule


# ─── SQL Generators ──────────────────────────────────────────────────────

class TestGenNotNull:
    def test_basic(self):
        rule = _make_rule(table_name="users")
        sql, meta = _gen_not_null(rule, {"field": "email"})
        assert "users" in sql
        assert "email IS NULL" in sql
        assert meta["pass_when"] == "eq_zero"


class TestGenUniqueness:
    def test_single_field(self):
        rule = _make_rule(table_name="accounts")
        sql, meta = _gen_uniqueness(rule, {"fields": ["account_id"]})
        assert "COUNT(*) - COUNT(DISTINCT account_id)" in sql
        assert "accounts" in sql
        assert meta["pass_when"] == "eq_zero"

    def test_multi_fields(self):
        rule = _make_rule(table_name="trades")
        sql, _ = _gen_uniqueness(rule, {"fields": ["trade_date", "trade_no"]})
        assert "trade_date, trade_no" in sql


class TestGenNullRate:
    def test_basic(self):
        rule = _make_rule(table_name="positions")
        sql, meta = _gen_null_rate(rule, {"field": "market_value", "threshold_pct": 10})
        assert "positions" in sql
        assert "market_value IS NULL" in sql
        assert meta["threshold"] == 10
        assert meta["pass_when"] == "lte"

    def test_default_threshold(self):
        rule = _make_rule(table_name="t")
        _, meta = _gen_null_rate(rule, {"field": "x"})
        assert meta["threshold"] == 5


class TestGenValueRange:
    def test_min_and_max(self):
        rule = _make_rule(table_name="nav")
        sql, meta = _gen_value_range(rule, {"field": "nav_value", "min_value": 0, "max_value": 100})
        assert "nav_value < 0" in sql
        assert "nav_value > 100" in sql
        assert meta["pass_when"] == "eq_zero"

    def test_only_max(self):
        rule = _make_rule(table_name="t")
        sql, _ = _gen_value_range(rule, {"field": "x", "max_value": 50})
        assert "x > 50" in sql
        assert "x <" not in sql


class TestGenRegexMatch:
    def test_basic(self):
        rule = _make_rule(table_name="clients")
        sql, meta = _gen_regex_match(rule, {"field": "phone", "pattern": "^1[3-9]\\d{9}$"})
        assert "REGEXP" in sql
        assert "phone" in sql
        assert meta["pass_when"] == "eq_zero"


class TestGenRowCount:
    def test_basic(self):
        rule = _make_rule(table_name="daily_nav")
        sql, meta = _gen_row_count(rule, {"threshold_pct": 30})
        assert "COUNT(*)" in sql
        assert "daily_nav" in sql
        assert meta["pass_when"] == "row_count_volatility"
        assert meta["threshold"] == 30


class TestGenTimeliness:
    def test_today(self):
        rule = _make_rule(table_name="market_data")
        sql, meta = _gen_timeliness(rule, {"date_field": "trade_date", "expected_date": "today"})
        assert "trade_date" in sql
        assert date.today().isoformat() in sql
        assert meta["pass_when"] == "gt_zero"

    def test_specific_date(self):
        rule = _make_rule(table_name="t")
        sql, _ = _gen_timeliness(rule, {"date_field": "dt", "expected_date": "2026-05-01"})
        assert "2026-05-01" in sql


class TestGenDictRef:
    def test_basic(self):
        rule = _make_rule(table_name="trades")
        sql, meta = _gen_dict_ref(rule, {
            "field": "security_type",
            "dict_table": "dim_security_type",
            "dict_field": "code",
        })
        assert "LEFT JOIN dim_security_type" in sql
        assert "a.security_type = b.code" in sql
        assert meta["pass_when"] == "eq_zero"


class TestGenCustomSql:
    def test_basic(self):
        rule = _make_rule()
        sql, meta = _gen_custom_sql(rule, {
            "sql": "SELECT COUNT(*) FROM orders WHERE amount < 0",
            "operator": "=",
            "threshold": 0,
        })
        assert sql == "SELECT COUNT(*) FROM orders WHERE amount < 0"
        assert meta["pass_when"] == "custom"
        assert meta["operator"] == "="
        assert meta["threshold"] == 0


class TestGenCrossTable:
    def test_returns_marker(self):
        rule = _make_rule()
        sql, config = _gen_cross_table_check(rule, {"ds_id_a": 1, "table_a": "t1"})
        assert sql == "__CROSS_TABLE__"


# ─── Evaluate ────────────────────────────────────────────────────────────

class TestEvaluate:
    def test_eq_zero_pass(self):
        assert _evaluate(0, {"pass_when": "eq_zero"}, _make_rule(), MagicMock()) == "pass"

    def test_eq_zero_fail(self):
        assert _evaluate(5, {"pass_when": "eq_zero"}, _make_rule(), MagicMock()) == "fail"

    def test_gt_zero_pass(self):
        assert _evaluate(1, {"pass_when": "gt_zero"}, _make_rule(), MagicMock()) == "pass"

    def test_gt_zero_fail(self):
        assert _evaluate(0, {"pass_when": "gt_zero"}, _make_rule(), MagicMock()) == "fail"

    def test_lte_pass(self):
        assert _evaluate(3.5, {"pass_when": "lte", "threshold": 5}, _make_rule(), MagicMock()) == "pass"

    def test_lte_fail(self):
        assert _evaluate(6.0, {"pass_when": "lte", "threshold": 5}, _make_rule(), MagicMock()) == "fail"

    def test_custom_operators(self):
        meta = {"pass_when": "custom", "operator": ">", "threshold": 10}
        assert _evaluate(15, meta, _make_rule(), MagicMock()) == "pass"
        assert _evaluate(5, meta, _make_rule(), MagicMock()) == "fail"

    def test_row_count_volatility_first_run(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        meta = {"pass_when": "row_count_volatility", "threshold": 50}
        assert _evaluate(1000, meta, _make_rule(), db) == "pass"

    def test_row_count_volatility_within_threshold(self):
        db = MagicMock()
        last_result = MagicMock()
        last_result.actual_value = 100.0
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = last_result
        meta = {"pass_when": "row_count_volatility", "threshold": 50}
        assert _evaluate(120, meta, _make_rule(), db) == "pass"

    def test_row_count_volatility_exceeds(self):
        db = MagicMock()
        last_result = MagicMock()
        last_result.actual_value = 100.0
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = last_result
        meta = {"pass_when": "row_count_volatility", "threshold": 50}
        assert _evaluate(200, meta, _make_rule(), db) == "fail"


# ─── Compare Datasets ─────────────────────────────────────────────────────

class TestCompareDatasets:
    def test_identical_datasets(self):
        rows_a = [(1, 100.0), (2, 200.0)]
        rows_b = [(1, 100.0), (2, 200.0)]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["val"], ["val"], 0)
        assert result["status"] == "pass"
        assert result["actual_value"] == 0

    def test_value_mismatch(self):
        rows_a = [(1, 100.0), (2, 200.0)]
        rows_b = [(1, 100.0), (2, 250.0)]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["val"], ["val"], 0)
        assert result["status"] == "fail"
        assert result["actual_value"] == 1

    def test_tolerance(self):
        rows_a = [(1, 100.0)]
        rows_b = [(1, 100.5)]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["val"], ["val"], 1.0)
        assert result["status"] == "pass"

    def test_missing_in_a(self):
        rows_a = [(1, 100.0)]
        rows_b = [(1, 100.0), (2, 200.0)]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["val"], ["val"], 0)
        assert result["status"] == "fail"
        assert result["detail"]["missing_in_a"] == 1

    def test_missing_in_b(self):
        rows_a = [(1, 100.0), (2, 200.0)]
        rows_b = [(1, 100.0)]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["val"], ["val"], 0)
        assert result["status"] == "fail"
        assert result["detail"]["missing_in_b"] == 1

    def test_string_comparison(self):
        rows_a = [(1, "active")]
        rows_b = [(1, "active")]
        result = compare_datasets(rows_a, rows_b, ["id"], ["id"], ["status"], ["status"], 0)
        assert result["status"] == "pass"


# ─── GENERATORS registry ──────────────────────────────────────────────────

def test_all_generators_registered():
    expected = {
        "not_null", "uniqueness", "null_rate", "value_range", "regex_match",
        "row_count", "timeliness", "dict_ref", "custom_sql", "cross_table_check",
    }
    assert set(GENERATORS.keys()) == expected
