"""TDD tests for component rename → workflow sync"""
import pytest
from unittest.mock import MagicMock, patch, call
import copy


def _make_workflow(dag_nodes=None, steps=None):
    wf = MagicMock()
    wf.dag_json = {"nodes": dag_nodes or [], "edges": []} if dag_nodes is not None else None
    wf.steps_json = steps
    return wf


class TestSyncComponentNameInWorkflows:
    def _call(self, db, comp_id, new_name):
        from app.api.component import _sync_component_name_in_workflows
        _sync_component_name_in_workflows(db, comp_id, new_name)

    def _make_db(self, workflows):
        db = MagicMock()
        db.query.return_value.all.return_value = workflows
        return db

    def test_updates_matching_dag_node(self):
        wf = _make_workflow(dag_nodes=[
            {"component_id": 42, "name": "old_name"},
            {"component_id": 99, "name": "other"},
        ])
        db = self._make_db([wf])
        self._call(db, comp_id=42, new_name="new_name")
        assert wf.dag_json["nodes"][0]["name"] == "new_name"
        assert wf.dag_json["nodes"][1]["name"] == "other"

    def test_does_not_touch_unrelated_nodes(self):
        wf = _make_workflow(dag_nodes=[
            {"component_id": 99, "name": "stays"},
        ])
        db = self._make_db([wf])
        original = copy.deepcopy(wf.dag_json)
        self._call(db, comp_id=42, new_name="new_name")
        assert wf.dag_json == original

    def test_updates_steps_json(self):
        wf = _make_workflow(steps=[
            {"component_id": 42, "name": "old"},
            {"component_id": 1, "name": "other"},
        ])
        db = self._make_db([wf])
        self._call(db, comp_id=42, new_name="renamed")
        assert wf.steps_json[0]["name"] == "renamed"
        assert wf.steps_json[1]["name"] == "other"

    def test_handles_null_dag_json(self):
        wf = MagicMock()
        wf.dag_json = None
        wf.steps_json = None
        db = self._make_db([wf])
        self._call(db, comp_id=42, new_name="x")  # should not raise

    def test_commits_once_after_changes(self):
        wf = _make_workflow(dag_nodes=[{"component_id": 42, "name": "old"}])
        db = self._make_db([wf])
        self._call(db, comp_id=42, new_name="new")
        db.commit.assert_called()

    def test_multiple_workflows_updated(self):
        wf1 = _make_workflow(dag_nodes=[{"component_id": 42, "name": "old"}])
        wf2 = _make_workflow(dag_nodes=[{"component_id": 42, "name": "old"}])
        db = self._make_db([wf1, wf2])
        self._call(db, comp_id=42, new_name="new")
        assert wf1.dag_json["nodes"][0]["name"] == "new"
        assert wf2.dag_json["nodes"][0]["name"] == "new"
