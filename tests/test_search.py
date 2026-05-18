"""Tests for advanced search routes."""
import json
from unittest.mock import patch


class TestMatchesFilter:
    """Unit tests for the _matches_filter helper."""

    def _get_fn(self):
        from app.routes.search import _matches_filter
        return _matches_filter

    def test_matches_filter_equals(self):
        fn = self._get_fn()
        result = {"status": "COMPLETED", "workflowType": "order_fulfillment"}
        assert fn(result, [{"path": "status", "operator": "eq", "value": "COMPLETED"}]) is True
        assert fn(result, [{"path": "status", "operator": "eq", "value": "FAILED"}]) is False

    def test_matches_filter_contains(self):
        fn = self._get_fn()
        result = {"correlationId": "order-1001-batch"}
        assert fn(result, [{"path": "correlationId", "operator": "contains", "value": "order-1001"}]) is True
        assert fn(result, [{"path": "correlationId", "operator": "contains", "value": "enrollment"}]) is False

    def test_matches_filter_nested_path(self):
        fn = self._get_fn()
        result = {"input": {"orderId": 1001, "customerId": "cust-A"}}
        assert fn(result, [{"path": "input.orderId", "operator": "eq", "value": "1001"}]) is True
        assert fn(result, [{"path": "input.customerId", "operator": "eq", "value": "cust-B"}]) is False

    def test_matches_filter_missing_field(self):
        fn = self._get_fn()
        result = {"status": "COMPLETED"}
        # "exists" on a missing field should fail
        assert fn(result, [{"path": "input.orderId", "operator": "exists", "value": ""}]) is False
        # "not_exists" on a missing field should pass
        assert fn(result, [{"path": "input.orderId", "operator": "not_exists", "value": ""}]) is True

    def test_matches_filter_neq(self):
        fn = self._get_fn()
        result = {"status": "FAILED"}
        assert fn(result, [{"path": "status", "operator": "neq", "value": "COMPLETED"}]) is True
        assert fn(result, [{"path": "status", "operator": "neq", "value": "FAILED"}]) is False

    def test_matches_filter_not_contains(self):
        fn = self._get_fn()
        result = {"correlationId": "order-1001"}
        assert fn(result, [{"path": "correlationId", "operator": "not_contains", "value": "enrollment"}]) is True
        assert fn(result, [{"path": "correlationId", "operator": "not_contains", "value": "order"}]) is False

    def test_matches_filter_multiple_filters_all_must_match(self):
        fn = self._get_fn()
        result = {"status": "COMPLETED", "workflowType": "order_fulfillment"}
        filters = [
            {"path": "status", "operator": "eq", "value": "COMPLETED"},
            {"path": "workflowType", "operator": "eq", "value": "order_fulfillment"},
        ]
        assert fn(result, filters) is True
        filters_fail = [
            {"path": "status", "operator": "eq", "value": "COMPLETED"},
            {"path": "workflowType", "operator": "eq", "value": "student_enrollment"},
        ]
        assert fn(result, filters_fail) is False


class TestAdvancedSearchEndpoint:
    """Integration tests for POST /api/v1/search/advanced."""

    def test_advanced_search_returns_results(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/advanced",
            data=json.dumps({"workflowType": "order_fulfillment", "status": "COMPLETED"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data
        assert "totalHits" in data
        assert "statusCounts" in data

    def test_advanced_search_with_filter(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/advanced",
            data=json.dumps({
                "filters": [{"path": "status", "operator": "eq", "value": "COMPLETED"}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # All returned results should be COMPLETED
        for r in data.get("results", []):
            assert r["status"] == "COMPLETED"

    def test_saved_search_crud(self, client_with_mock_conductor):
        # Create
        resp = client_with_mock_conductor.post(
            "/api/v1/search/saved",
            data=json.dumps({"name": "Test Search", "searchConfig": {"status": "FAILED"}}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        created = resp.get_json()
        assert created["name"] == "Test Search"
        search_id = created["id"]

        # List
        resp = client_with_mock_conductor.get("/api/v1/search/saved")
        assert resp.status_code == 200
        searches = resp.get_json()
        assert any(s["id"] == search_id for s in searches)

        # Delete
        resp = client_with_mock_conductor.delete(f"/api/v1/search/saved/{search_id}")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "conductor-companion"
        assert "uptime_seconds" in data

    def test_export_csv_returns_csv(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/export",
            data=json.dumps({"workflowType": "order_fulfillment"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_csv_has_header_row(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/export",
            data=json.dumps({}),
            content_type="application/json",
        )
        csv_content = resp.data.decode("utf-8")
        assert "workflowId" in csv_content
        assert "status" in csv_content

    def test_export_csv_with_filters(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/export",
            data=json.dumps({
                "filters": [{"path": "status", "operator": "eq", "value": "COMPLETED"}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_advanced_search_error_path(self, client_with_mock_conductor, mock_conductor):
        mock_conductor.search.side_effect = Exception("conductor unreachable")
        resp = client_with_mock_conductor.post(
            "/api/v1/search/advanced",
            data=json.dumps({"workflowType": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 500
        # Reset side effect
        import time
        now_ms = int(time.time() * 1000)
        mock_conductor.search.side_effect = None
        mock_conductor.search.return_value = {"totalHits": 0, "results": []}

    def test_delete_nonexistent_saved_search_returns_404(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.delete("/api/v1/search/saved/99999")
        assert resp.status_code == 404

    def test_create_saved_search_missing_name(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/search/saved",
            data=json.dumps({"description": "no name"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"
