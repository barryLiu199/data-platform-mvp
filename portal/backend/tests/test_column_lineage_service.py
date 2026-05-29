"""Tests for app/core/column_lineage_service.py — 三类解析 + 失败隔离 + BFS"""
import json
import pytest
from unittest.mock import MagicMock

from app.core.column_lineage_service import (
    _norm,
    _parse_sync_task,
    _parse_component_datax,
    _parse_component_sql,
    _parse_sql_columns,
    refresh_column_lineage,
    build_column_lineage,
)
from app.models.column_lineage import ColumnLineage, ColumnParseFailure
from app.models.component import Component
from app.models.sync_task import SyncTask


# ─── _norm ──────────────────────────────────────────────────────────────

def test_norm_lowers_and_strips_quotes():
    assert _norm('`Order_ID`') == "order_id"
    assert _norm('"User"') == "user"
    assert _norm("  Foo  ") == "foo"
    assert _norm(None) == ""
    assert _norm("") == ""


# ─── SyncTask parser ────────────────────────────────────────────────────

class TestParseSyncTask:
    def _task(self, mapping, **kw):
        t = SyncTask(
            id=kw.get("id", 1),
            name=kw.get("name", "t1"),
            source_id=10, target_id=20,
            source_table=kw.get("source_table", "ods_user"),
            target_table=kw.get("target_table", "dw_user"),
            field_mapping=json.dumps(mapping) if mapping is not None else None,
            status="active",
        )
        return t

    def test_identity_mapping(self):
        task = self._task([
            {"kind": "column", "src": "id", "dst": "user_id"},
            {"kind": "column", "src": "Name", "dst": "user_name"},
        ])
        rows = _parse_sync_task(task)
        assert len(rows) == 2
        assert rows[0].source_table == "ods_user"
        assert rows[0].source_column == "id"
        assert rows[0].target_table == "dw_user"
        assert rows[0].target_column == "user_id"
        assert rows[0].transform_type == "identity"
        assert rows[0].entity_type == "sync_task"
        assert rows[0].parse_type == "datax"

    def test_skip_variable_and_constant(self):
        task = self._task([
            {"kind": "column", "src": "a", "dst": "x"},
            {"kind": "variable", "src": "${bizdate}", "dst": "dt"},
            {"kind": "constant", "src": "1", "dst": "flag"},
        ])
        rows = _parse_sync_task(task)
        assert len(rows) == 1

    def test_invalid_json_returns_empty(self):
        task = SyncTask(id=1, name="t", source_id=1, target_id=2,
                        source_table="a", target_table="b",
                        field_mapping="not-json", status="active")
        assert _parse_sync_task(task) == []

    def test_empty_mapping(self):
        task = self._task([])
        assert _parse_sync_task(task) == []

    def test_missing_tables(self):
        task = self._task([{"kind": "column", "src": "x", "dst": "y"}],
                          source_table=None, target_table="b")
        assert _parse_sync_task(task) == []


# ─── DataX component parser ─────────────────────────────────────────────

class TestParseComponentDataX:
    def _comp(self, raw_json):
        c = Component(
            id=2, name="datax_comp", type="datax", status="online",
            config_json={"rawJson": json.dumps(raw_json),
                         "source_id": 10, "target_id": 20},
        )
        return c

    def test_basic_position_alignment(self):
        raw = {
            "job": {"content": [{
                "reader": {"parameter": {
                    "connection": [{"table": ["ods_t"]}],
                    "column": ["id", "name", "age"],
                }},
                "writer": {"parameter": {
                    "connection": [{"table": ["dw_t"]}],
                    "column": ["user_id", "user_name", "user_age"],
                }},
            }]}
        }
        rows = _parse_component_datax(self._comp(raw))
        assert len(rows) == 3
        assert (rows[0].source_column, rows[0].target_column) == ("id", "user_id")
        assert (rows[2].source_column, rows[2].target_column) == ("age", "user_age")
        assert rows[0].transform_type == "identity"
        assert rows[0].source_ds_id == 10
        assert rows[0].target_ds_id == 20

    def test_dict_columns(self):
        raw = {
            "job": {"content": [{
                "reader": {"parameter": {
                    "connection": [{"table": ["src"]}],
                    "column": [{"name": "Col_A", "type": "BIGINT"}, {"name": "Col_B"}],
                }},
                "writer": {"parameter": {
                    "connection": [{"table": ["dst"]}],
                    "column": [{"name": "a"}, {"name": "b"}],
                }},
            }]}
        }
        rows = _parse_component_datax(self._comp(raw))
        assert len(rows) == 2
        assert rows[0].source_column == "col_a"

    def test_min_truncation(self):
        raw = {
            "job": {"content": [{
                "reader": {"parameter": {
                    "connection": [{"table": ["s"]}],
                    "column": ["a", "b", "c"],
                }},
                "writer": {"parameter": {
                    "connection": [{"table": ["t"]}],
                    "column": ["x"],
                }},
            }]}
        }
        rows = _parse_component_datax(self._comp(raw))
        assert len(rows) == 1

    def test_missing_tables(self):
        raw = {"job": {"content": [{"reader": {"parameter": {}}, "writer": {"parameter": {}}}]}}
        assert _parse_component_datax(self._comp(raw)) == []


# ─── SQL parser ─────────────────────────────────────────────────────────

class TestParseSqlColumns:
    def test_simple_insert_select(self):
        sql = """
        INSERT INTO dw_orders
        SELECT order_id, user_id, amount
        FROM ods_orders
        """
        edges = _parse_sql_columns(sql)
        assert len(edges) >= 3
        keys = {(e["src_col"], e["tgt_col"]) for e in edges}
        assert ("order_id", "order_id") in keys
        assert ("amount", "amount") in keys

    def test_aggregate(self):
        sql = """
        INSERT INTO dw_summary
        SELECT user_id, SUM(amount) AS total
        FROM ods_orders
        GROUP BY user_id
        """
        edges = _parse_sql_columns(sql)
        agg = [e for e in edges if e["tgt_col"] == "total"]
        assert agg
        assert agg[0]["transform_type"] == "aggregate"
        assert "SUM" in (agg[0]["transform_expr"] or "").upper()

    def test_alias_identity(self):
        sql = "INSERT INTO t SELECT a AS b FROM src"
        edges = _parse_sql_columns(sql)
        # b 来源 src.a，且 transform_type=identity
        rec = [e for e in edges if e["tgt_col"] == "b"]
        assert rec
        assert rec[0]["transform_type"] == "identity"

    def test_no_target_returns_empty(self):
        sql = "SELECT x FROM y"
        # 没有 INSERT/CREATE 也没有 default target
        assert _parse_sql_columns(sql) == []

    def test_default_target_table(self):
        sql = "SELECT a FROM src"
        edges = _parse_sql_columns(sql, default_target_table="my_tgt")
        assert edges
        assert all(e["tgt_table"] == "my_tgt" for e in edges)


# ─── refresh_column_lineage 集成 ─────────────────────────────────────────

class TestRefreshColumnLineage:
    def test_idempotent_refresh(self, db_session, clean_tables):
        # 准备一个 sync_task
        task = SyncTask(
            id=901,
            name="t1", source_id=1, target_id=2,
            source_table="ods_a", target_table="dw_a",
            field_mapping=json.dumps([
                {"kind": "column", "src": "id", "dst": "id"},
                {"kind": "column", "src": "n", "dst": "name"},
            ]),
            status="active",
        )
        db_session.add(task)
        db_session.commit()

        stats1 = refresh_column_lineage(db_session)
        assert stats1["sync_task"] == 2
        rows1 = db_session.query(ColumnLineage).count()
        assert rows1 == 2

        # 再跑一次 — 行数不变（幂等）
        stats2 = refresh_column_lineage(db_session)
        assert stats2["sync_task"] == 2
        assert db_session.query(ColumnLineage).count() == 2

    def test_manual_rows_preserved(self, db_session, clean_tables):
        # 写入一条 manual 行
        manual = ColumnLineage(
            source_table="ods_x", source_column="a",
            target_table="dw_x", target_column="b",
            entity_type="manual", entity_name="手工补登",
            transform_type="identity", parse_type="manual", parse_status="ok",
        )
        db_session.add(manual)
        db_session.commit()

        stats = refresh_column_lineage(db_session)
        assert stats["manual_kept"] == 1
        # manual 行依然存在
        assert db_session.query(ColumnLineage).filter(
            ColumnLineage.entity_type == "manual"
        ).count() == 1

    def test_failure_isolation(self, db_session, clean_tables):
        # 两个组件：一个 SQL 解析正常，一个故意造解析错误
        good = Component(
            id=801,
            name="good", type="sql", status="online",
            config_json={"sql": "INSERT INTO t1 SELECT a FROM s1", "datasource_id": 1},
        )
        bad = Component(
            id=802,
            name="bad", type="sql", status="online",
            config_json={"sql": "this is not valid sql at all !!!", "datasource_id": 1},
        )
        db_session.add_all([good, bad])
        db_session.commit()

        stats = refresh_column_lineage(db_session)
        # good 仍然产生边；bad 失败被隔离
        assert stats["component_sql"] >= 1
        # 解析失败的有 0 或 1 行（sqlglot 容错性高，可能不会抛错）
        # 关键断言：不抛异常 + 整体未崩
        assert "duration_ms" in stats


# ─── build_column_lineage BFS ───────────────────────────────────────────

class TestBuildColumnLineage:
    def test_upstream_and_downstream(self, db_session, clean_tables):
        # ods_a.id → dw_a.id → ads_a.id
        rows = [
            ColumnLineage(source_table="ods_a", source_column="id",
                          target_table="dw_a", target_column="id",
                          entity_type="sync_task", entity_id=1, entity_name="t1",
                          transform_type="identity", parse_type="datax",
                          parse_status="ok"),
            ColumnLineage(source_table="dw_a", source_column="id",
                          target_table="ads_a", target_column="id",
                          entity_type="component", entity_id=2, entity_name="c1",
                          transform_type="identity", parse_type="sqlglot",
                          parse_status="ok"),
        ]
        db_session.add_all(rows)
        db_session.commit()

        graph = build_column_lineage(db_session, "dw_a", "id", depth=3, direction="both")
        # 中心 + 上游 + 下游 = 3 节点；2 条边
        assert graph["stats"]["total_nodes"] == 3
        assert graph["stats"]["total_edges"] == 2

    def test_upstream_only(self, db_session, clean_tables):
        db_session.add(ColumnLineage(
            source_table="ods_x", source_column="a",
            target_table="dw_x", target_column="b",
            entity_type="manual", entity_name="m",
            transform_type="identity", parse_type="manual", parse_status="ok",
        ))
        db_session.commit()
        graph = build_column_lineage(db_session, "dw_x", "b",
                                     depth=2, direction="upstream")
        assert graph["stats"]["total_edges"] == 1
        assert graph["stats"]["total_nodes"] == 2

    def test_no_lineage(self, db_session, clean_tables):
        graph = build_column_lineage(db_session, "nonexistent", "x")
        assert graph["stats"]["total_nodes"] == 1  # 仅中心节点
        assert graph["stats"]["total_edges"] == 0
