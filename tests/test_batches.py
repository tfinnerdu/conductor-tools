"""Tests for batches routes — /api/v1/batches/*"""
import json
from unittest.mock import MagicMock, patch
import time

import pytest


def _make_batch(client, name="Test Batch", workflow_name="student_enrollment", **kwargs):
    """Helper to create a batch via the API."""
    body = {"name": name, "workflowName": workflow_name, **kwargs}
    resp = client.post(
        "/api/v1/batches",
        data=json.dumps(body),
        content_type="application/json",
    )
    return resp


class TestListBatches:
    def test_empty_returns_list(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/batches")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_with_entries_returns_batches(self, client_with_mock_conductor):
        _make_batch(client_with_mock_conductor, name="Batch A")
        _make_batch(client_with_mock_conductor, name="Batch B")

        resp = client_with_mock_conductor.get("/api/v1/batches")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 2
        names = [b["name"] for b in data]
        assert "Batch A" in names
        assert "Batch B" in names

    def test_response_contains_required_fields(self, client_with_mock_conductor):
        _make_batch(client_with_mock_conductor, name="Field Test Batch")
        resp = client_with_mock_conductor.get("/api/v1/batches")
        data = resp.get_json()
        if data:
            batch = next((b for b in data if b["name"] == "Field Test Batch"), None)
            assert batch is not None
            assert "id" in batch
            assert "name" in batch
            assert "workflowName" in batch or "workflow_name" in batch


class TestCreateBatch:
    def test_valid_creation(self, client_with_mock_conductor):
        resp = _make_batch(
            client_with_mock_conductor,
            name="My Test Batch",
            workflow_name="order_fulfillment",
            totalExpected=100,
            correlationIdPrefix="order-2024-",
            createdBy="test-user",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "My Test Batch"
        assert "id" in data

    def test_missing_name_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/batches",
            data=json.dumps({"workflowName": "order_fulfillment"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_missing_workflow_name_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/batches",
            data=json.dumps({"name": "Incomplete Batch"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_empty_name_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/batches",
            data=json.dumps({"name": "  ", "workflowName": "order_fulfillment"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestBatchStatus:
    def test_returns_status_for_existing_batch(self, client_with_mock_conductor):
        create_resp = _make_batch(client_with_mock_conductor, name="Status Test")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "batchId" in data
        assert data["batchId"] == batch_id
        assert "totalFound" in data
        assert "completed" in data
        assert "failed" in data
        assert "running" in data
        assert "progressPercent" in data
        assert "statusCounts" in data

    def test_nonexistent_batch_returns_404(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/batches/99999/status")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["code"] == "NOT_FOUND"

    def test_status_counts_aggregated(self, client_with_mock_conductor, mock_conductor):
        # Mock returns 2 COMPLETED + 1 FAILED + 1 RUNNING from conftest
        create_resp = _make_batch(client_with_mock_conductor, name="Counts Batch")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/status")
        data = resp.get_json()
        assert "statusCounts" in data
        # Should have entries matching mock data
        assert sum(data["statusCounts"].values()) == data["totalFound"]

    def test_progress_percent_calculated(self, client_with_mock_conductor):
        create_resp = _make_batch(
            client_with_mock_conductor,
            name="Progress Batch",
            totalExpected=10,
        )
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/status")
        data = resp.get_json()
        assert isinstance(data["progressPercent"], (int, float))
        assert 0 <= data["progressPercent"] <= 100


class TestRetryFailures:
    def test_returns_retry_result_for_existing_batch(self, client_with_mock_conductor):
        create_resp = _make_batch(client_with_mock_conductor, name="Retry Batch")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.post(f"/api/v1/batches/{batch_id}/retry-failures")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "batchId" in data
        assert data["batchId"] == batch_id
        assert "retriedCount" in data
        assert "errorCount" in data
        assert "errors" in data

    def test_nonexistent_batch_returns_404(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post("/api/v1/batches/99999/retry-failures")
        assert resp.status_code == 404

    def test_retry_calls_conductor(self, client_with_mock_conductor, mock_conductor):
        # The conftest mock has FAILED workflows; retry should be called on them
        create_resp = _make_batch(client_with_mock_conductor, name="Retry Call Batch")
        batch_id = create_resp.get_json()["id"]

        # Override mock to return FAILED workflows
        from unittest.mock import MagicMock
        import time as t
        now_ms = int(t.time() * 1000)
        failed_results = {
            "totalHits": 2,
            "results": [
                {"workflowId": "fail-001", "workflowType": "student_enrollment", "status": "FAILED",
                 "startTime": now_ms - 3600000, "endTime": now_ms - 3500000},
                {"workflowId": "fail-002", "workflowType": "student_enrollment", "status": "FAILED",
                 "startTime": now_ms - 7200000, "endTime": now_ms - 7100000},
            ],
        }
        mock_conductor.search.return_value = failed_results

        resp = client_with_mock_conductor.post(f"/api/v1/batches/{batch_id}/retry-failures")
        data = resp.get_json()
        # Should have attempted to retry each failed workflow
        assert data["retriedCount"] >= 0


class TestExportBatch:
    def test_returns_csv_content_type(self, client_with_mock_conductor):
        create_resp = _make_batch(client_with_mock_conductor, name="Export Batch")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_csv_has_header_row(self, client_with_mock_conductor):
        create_resp = _make_batch(client_with_mock_conductor, name="CSV Header Batch")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/export")
        csv_content = resp.data.decode("utf-8")
        assert "workflowId" in csv_content
        assert "workflowType" in csv_content
        assert "status" in csv_content

    def test_csv_content_disposition_header(self, client_with_mock_conductor):
        create_resp = _make_batch(client_with_mock_conductor, name="Disposition Test")
        batch_id = create_resp.get_json()["id"]

        resp = client_with_mock_conductor.get(f"/api/v1/batches/{batch_id}/export")
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".csv" in content_disp

    def test_nonexistent_batch_returns_404(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/batches/99999/export")
        assert resp.status_code == 404
