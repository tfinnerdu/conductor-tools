"""Tests for diff routes — /api/v1/diff/*"""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestFlattenTasks:
    """Unit tests for the flatten_tasks helper (if it exists) or nested task handling."""

    def _get_render_diff(self):
        from app.routes.diff import _render_diff_html
        return _render_diff_html

    def _get_significant_changes(self):
        from app.routes.diff import _significant_changes
        return _significant_changes

    def _get_extract_task_lines(self):
        from app.routes.diff import _extract_task_lines
        return _extract_task_lines

    def test_render_diff_added_lines(self):
        fn = self._get_render_diff()
        lines_a = ["line1", "line2"]
        lines_b = ["line1", "line2", "line3"]
        result = fn(lines_a, lines_b)
        assert isinstance(result, list)
        added = [d for d in result if d["type"] == "added"]
        assert len(added) > 0

    def test_render_diff_removed_lines(self):
        fn = self._get_render_diff()
        lines_a = ["line1", "line2", "line3"]
        lines_b = ["line1", "line2"]
        result = fn(lines_a, lines_b)
        removed = [d for d in result if d["type"] == "removed"]
        assert len(removed) > 0

    def test_render_diff_identical_lines(self):
        fn = self._get_render_diff()
        lines = ["line1", "line2"]
        result = fn(lines, lines)
        # No added or removed when identical
        assert not any(d["type"] in ("added", "removed") for d in result)

    def test_render_diff_has_type_field(self):
        fn = self._get_render_diff()
        result = fn(["a", "b"], ["a", "c"])
        for item in result:
            assert "type" in item
            assert item["type"] in ("added", "removed", "context", "header")

    def test_significant_changes_filters_relevant(self):
        fn = self._get_significant_changes()
        diff_lines = [
            {"line": '  "name": "task_a"', "type": "added"},
            {"line": '  "someOtherKey": "value"', "type": "added"},
            {"line": '  "type": "SIMPLE"', "type": "removed"},
            {"line": "@@ -1,2 +1,3 @@", "type": "header"},
        ]
        result = fn(diff_lines)
        result_lines = [d["line"] for d in result]
        # Should include "name" and "type" lines
        assert any('"name"' in line for line in result_lines)
        assert any('"type"' in line for line in result_lines)
        # Should include headers
        assert any("@@" in line for line in result_lines)

    def test_significant_changes_excludes_non_significant(self):
        fn = self._get_significant_changes()
        diff_lines = [
            {"line": '  "description": "changed desc"', "type": "added"},
            {"line": '  "ownerEmail": "new@doane.edu"', "type": "removed"},
        ]
        result = fn(diff_lines)
        # Neither "description" nor "ownerEmail" are significant keys
        assert result == []

    def test_extract_task_lines_returns_list_of_strings(self):
        fn = self._get_extract_task_lines()
        definition = {
            "tasks": [
                {"name": "task_a", "taskReferenceName": "ref_a", "type": "SIMPLE"},
                {"name": "task_b", "taskReferenceName": "ref_b", "type": "SIMPLE"},
            ]
        }
        result = fn(definition)
        assert isinstance(result, list)
        assert all(isinstance(line, str) for line in result)
        # JSON content should be present
        full = "\n".join(result)
        assert "task_a" in full

    def test_extract_task_lines_empty_tasks(self):
        fn = self._get_extract_task_lines()
        result = fn({})
        assert isinstance(result, list)


class TestListWorkflows:
    def test_returns_workflow_list(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_groups_by_name(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        data = resp.get_json()
        names = [wf["name"] for wf in data]
        # conftest mock has order_fulfillment v1 and v2 — should be grouped
        assert "order_fulfillment" in names
        assert "student_enrollment" in names
        # order_fulfillment appears only once in the list (grouped)
        assert names.count("order_fulfillment") == 1

    def test_each_entry_has_versions(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        data = resp.get_json()
        for wf in data:
            assert "name" in wf
            assert "versions" in wf
            assert isinstance(wf["versions"], list)
            assert len(wf["versions"]) > 0

    def test_order_fulfillment_has_two_versions(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        data = resp.get_json()
        order_wf = next((w for w in data if w["name"] == "order_fulfillment"), None)
        assert order_wf is not None
        assert len(order_wf["versions"]) == 2

    def test_sorted_by_name(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        data = resp.get_json()
        names = [wf["name"] for wf in data]
        assert names == sorted(names)


class TestDiffWorkflow:
    def test_full_mode_returns_diff(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({
                "workflowName": "order_fulfillment",
                "versionA": 1,
                "versionB": 2,
                "mode": "full",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "workflowName" in data
        assert "diffLines" in data
        assert "summary" in data
        assert "addedLines" in data["summary"]
        assert "removedLines" in data["summary"]

    def test_tasks_only_mode(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({
                "workflowName": "order_fulfillment",
                "versionA": 1,
                "versionB": 2,
                "mode": "tasks",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "tasks"

    def test_significant_mode(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({
                "workflowName": "order_fulfillment",
                "versionA": 1,
                "versionB": 2,
                "mode": "significant",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "significant"
        # Significant mode should only return meaningful changes
        for line in data["diffLines"]:
            if line["type"] in ("added", "removed"):
                from app.routes.diff import _significant_changes
                sig_keys = {"name", "taskReferenceName", "type", "inputParameters"}
                assert any(f'"{k}"' in line["line"] for k in sig_keys), \
                    f"Non-significant line in significant mode: {line['line']!r}"

    def test_missing_workflow_name_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({"versionA": 1, "versionB": 2}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_missing_version_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({"workflowName": "order_fulfillment", "versionA": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_same_version_produces_no_diff(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({
                "workflowName": "order_fulfillment",
                "versionA": 1,
                "versionB": 1,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # Same version = no additions or removals
        assert data["summary"]["addedLines"] == 0
        assert data["summary"]["removedLines"] == 0

    def test_response_has_version_fields(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/workflow",
            data=json.dumps({
                "workflowName": "order_fulfillment",
                "versionA": 1,
                "versionB": 2,
            }),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["versionA"] == 1
        assert data["versionB"] == 2
        assert data["workflowName"] == "order_fulfillment"


class TestDependencyMap:
    def test_returns_graph(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "totalWorkflows" in data

    def test_nodes_have_required_fields(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        data = resp.get_json()
        for node in data["nodes"]:
            assert "workflowName" in node
            assert "version" in node
            assert "taskTypes" in node
            assert isinstance(node["taskTypes"], list)

    def test_total_workflows_matches_nodes(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        data = resp.get_json()
        assert data["totalWorkflows"] == len(data["nodes"])

    def test_task_types_are_sorted(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        data = resp.get_json()
        for node in data["nodes"]:
            task_types = node["taskTypes"]
            assert task_types == sorted(task_types)


class TestImpactAnalysis:
    def test_known_task_type_finds_workflows(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/impact",
            data=json.dumps({"taskType": "validate_order"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "taskType" in data
        assert data["taskType"] == "validate_order"
        assert "impactedWorkflows" in data
        assert "impactedCount" in data
        assert data["impactedCount"] > 0

    def test_unknown_task_type_returns_empty(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/impact",
            data=json.dumps({"taskType": "nonexistent_task_xyz"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["impactedCount"] == 0
        assert data["impactedWorkflows"] == []

    def test_missing_task_type_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/impact",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_impacted_workflow_has_task_references(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/impact",
            data=json.dumps({"taskType": "validate_order"}),
            content_type="application/json",
        )
        data = resp.get_json()
        for wf in data["impactedWorkflows"]:
            assert "workflowName" in wf
            assert "version" in wf
            assert "taskReferences" in wf
            assert isinstance(wf["taskReferences"], list)

    def test_impacted_count_matches_list(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/diff/impact",
            data=json.dumps({"taskType": "validate_order"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["impactedCount"] == len(data["impactedWorkflows"])
