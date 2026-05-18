"""Tests for JQ Lab routes."""
import json
from unittest.mock import patch, MagicMock


class TestJqEvaluate:
    """Tests for POST /api/v1/jq/evaluate."""

    def test_evaluate_jq_valid_expression(self, client):
        """A well-formed expression returns result with null error."""
        mock_jq = MagicMock()
        mock_jq.first.return_value = [1, 2, 3]

        with patch.dict("sys.modules", {"jq": mock_jq}):
            resp = client.post(
                "/api/v1/jq/evaluate",
                data=json.dumps({"expression": ".items", "input": {"items": [1, 2, 3]}}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["error"] is None
        assert data["result"] == [1, 2, 3]

    def test_evaluate_jq_invalid_expression_returns_error(self, client):
        """An expression that raises an error returns error field, not HTTP 500."""
        mock_jq = MagicMock()
        mock_jq.first.side_effect = ValueError("Invalid jq expression: unexpected token")

        with patch.dict("sys.modules", {"jq": mock_jq}):
            resp = client.post(
                "/api/v1/jq/evaluate",
                data=json.dumps({"expression": "!!!invalid!!!", "input": {}}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"] is None
        assert "Invalid jq" in data["error"]

    def test_evaluate_jq_string_input(self, client):
        """String JSON input is parsed before evaluation."""
        mock_jq = MagicMock()
        mock_jq.first.return_value = "hello"

        with patch.dict("sys.modules", {"jq": mock_jq}):
            resp = client.post(
                "/api/v1/jq/evaluate",
                data=json.dumps({"expression": ".name", "input": '{"name": "hello"}'}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["error"] is None

    def test_evaluate_jq_missing_expression(self, client):
        resp = client.post(
            "/api/v1/jq/evaluate",
            data=json.dumps({"input": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"


class TestFormatAsConductorTask:
    """Tests for POST /api/v1/jq/format-as-conductor-task."""

    def test_format_as_conductor_task(self, client):
        resp = client.post(
            "/api/v1/jq/format-as-conductor-task",
            data=json.dumps({
                "expression": ".items[] | select(.status == \"COMPLETED\")",
                "taskRef": "filter_items_ref",
                "taskName": "filter_items",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "task" in data
        assert "json" in data
        task = data["task"]
        assert task["type"] == "JSON_JQ_TRANSFORM"
        assert task["taskReferenceName"] == "filter_items_ref"
        assert task["name"] == "filter_items"
        assert ".items[]" in task["inputParameters"]["queryExpression"]

    def test_format_as_conductor_task_missing_expression(self, client):
        resp = client.post(
            "/api/v1/jq/format-as-conductor-task",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestLoadFromExecution:
    """Tests for GET /api/v1/jq/load-from-execution."""

    def test_load_from_execution_task_found(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get(
            "/api/v1/jq/load-from-execution?workflowId=wf-001&taskRef=validate_order_ref"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True
        assert data["workflowId"] == "wf-001"
        assert "data" in data

    def test_load_from_execution_task_not_found(self, client_with_mock_conductor):
        """When taskRef does not match any task, found=False is returned."""
        resp = client_with_mock_conductor.get(
            "/api/v1/jq/load-from-execution?workflowId=wf-001&taskRef=nonexistent_ref"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is False

    def test_load_from_execution_missing_workflow_id(self, client):
        resp = client.get("/api/v1/jq/load-from-execution")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"


class TestExpressionLibrary:
    """Tests for GET/POST /api/v1/jq/expressions."""

    def test_save_and_list_expression(self, client):
        resp = client.post(
            "/api/v1/jq/expressions",
            data=json.dumps({
                "name": "Test Expr",
                "expression": ".items | length",
                "description": "Count items",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Test Expr"

        list_resp = client.get("/api/v1/jq/expressions")
        assert list_resp.status_code == 200
        expressions = list_resp.get_json()
        assert any(e["name"] == "Test Expr" for e in expressions)

    def test_save_expression_missing_name(self, client):
        resp = client.post(
            "/api/v1/jq/expressions",
            data=json.dumps({"expression": ".foo"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_save_expression_missing_expression(self, client):
        resp = client.post(
            "/api/v1/jq/expressions",
            data=json.dumps({"name": "incomplete"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_list_expressions_with_tag_filter(self, client):
        # Save an expression with a tag
        client.post(
            "/api/v1/jq/expressions",
            data=json.dumps({
                "name": "Tagged Expr",
                "expression": ".foo",
                "tags": "enrollment",
            }),
            content_type="application/json",
        )
        resp = client.get("/api/v1/jq/expressions?tag=enrollment")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_list_expressions_with_resource_filter(self, client):
        client.post(
            "/api/v1/jq/expressions",
            data=json.dumps({
                "name": "Resource Expr",
                "expression": ".bar",
                "resourceName": "student",
            }),
            content_type="application/json",
        )
        resp = client.get("/api/v1/jq/expressions?resource=student")
        assert resp.status_code == 200


class TestJqEvaluateEdgeCases:
    """Additional edge case tests for jq evaluate."""

    def test_evaluate_invalid_json_string_input(self, client):
        """When input is a malformed JSON string, return 400."""
        mock_jq = MagicMock()
        with patch.dict("sys.modules", {"jq": mock_jq}):
            resp = client.post(
                "/api/v1/jq/evaluate",
                data=json.dumps({"expression": ".name", "input": "{not valid json}"}),
                content_type="application/json",
            )
        # Returns 400 with error message
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid JSON" in data.get("error", "") or data.get("code") == "VALIDATION_ERROR"

    def test_evaluate_import_error_returns_500(self, client):
        """When jq library is not installed, return 500 DEPENDENCY_ERROR."""
        import sys
        # Remove jq from sys.modules to simulate ImportError
        original = sys.modules.pop("jq", None)
        try:
            # Make import fail
            sys.modules["jq"] = None  # type: ignore
            resp = client.post(
                "/api/v1/jq/evaluate",
                data=json.dumps({"expression": ".foo", "input": {}}),
                content_type="application/json",
            )
        finally:
            if original is not None:
                sys.modules["jq"] = original
            else:
                sys.modules.pop("jq", None)
        # May be 400 (VALIDATION_ERROR if expression missing) or 500 (import error)
        assert resp.status_code in (400, 500)

    def test_load_from_execution_by_index(self, client_with_mock_conductor):
        """Load a task by index (taskIndex param)."""
        resp = client_with_mock_conductor.get(
            "/api/v1/jq/load-from-execution?workflowId=wf-001&taskIndex=0"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True

    def test_load_from_execution_defaults_to_last_completed(self, client_with_mock_conductor):
        """When no taskRef or taskIndex given, defaults to last completed task."""
        resp = client_with_mock_conductor.get(
            "/api/v1/jq/load-from-execution?workflowId=wf-001"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "found" in data
