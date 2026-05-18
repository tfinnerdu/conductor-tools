"""Tests for the Error Reconciler routes and helpers."""
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# _extract_error_code tests
# ---------------------------------------------------------------------------

def test_extract_error_code_duplicate_value():
    from app.routes.reconciler import _extract_error_code
    assert _extract_error_code("DUPLICATE_VALUE: SIS_ID already exists") == "DUPLICATE_VALUE"


def test_extract_error_code_http_error():
    from app.routes.reconciler import _extract_error_code
    assert _extract_error_code("HTTP 404 Not Found") == "HTTP_404"
    assert _extract_error_code("status 429 Too Many Requests") == "HTTP_429"
    assert _extract_error_code("HTTP_500 Internal Server Error") == "HTTP_500"


def test_extract_error_code_timeout():
    from app.routes.reconciler import _extract_error_code
    assert _extract_error_code("Task timed out after 30s") == "TIMEOUT"
    assert _extract_error_code("deadline exceeded") == "TIMEOUT"
    assert _extract_error_code("Connection timeout") == "TIMEOUT"


def test_extract_error_code_fallback():
    from app.routes.reconciler import _extract_error_code
    long_reason = "Something completely custom and unique without a pattern"
    result = _extract_error_code(long_reason)
    assert len(result) <= 60
    assert result == long_reason[:60]


def test_extract_error_code_empty():
    from app.routes.reconciler import _extract_error_code
    assert _extract_error_code("") == "UNKNOWN"
    assert _extract_error_code(None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# /failures endpoint tests
# ---------------------------------------------------------------------------

def _make_mock_conductor_with_failures():
    mock = MagicMock()
    mock.get_failures_by_task_type.return_value = {
        "workflow_name": "student_enrollment",
        "hours_back": 24,
        "groups": [
            {
                "task_type": "ethos_get_person",
                "count": 5,
                "reasons": {"HTTP_404": 3, "TIMEOUT": 2},
                "workflow_ids": ["wf-fail-001", "wf-fail-002", "wf-fail-003", "wf-fail-004", "wf-fail-005"],
            },
        ],
        "total_failures": 5,
    }
    mock.list_workflow_definitions.return_value = [
        {"name": "student_enrollment", "version": 1},
    ]
    mock.retry_workflow.return_value = None
    return mock


def test_failures_endpoint_returns_grouped_data(client):
    mock = _make_mock_conductor_with_failures()
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/reconciler/failures?workflow_name=student_enrollment&hours_back=24")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "groups" in data
    assert data["total"] >= 1
    groups = data["groups"]
    assert len(groups) >= 1
    first_group = groups[0]
    assert "task_type" in first_group
    assert "count" in first_group
    assert "reasons" in first_group
    assert "workflow_ids" in first_group


def test_failures_endpoint_pagination(client):
    mock = _make_mock_conductor_with_failures()
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/reconciler/failures?page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["page"] == 1
    assert data["per_page"] == 10


def test_failure_detail_endpoint(client):
    mock = MagicMock()
    mock.get_execution.return_value = {
        "workflowId": "wf-fail-001",
        "workflowType": "student_enrollment",
        "status": "FAILED",
        "startTime": 1700000000000,
        "endTime": 1700000060000,
        "input": {"sis_id": "SIS123"},
        "tasks": [
            {
                "taskId": "task-001",
                "taskType": "ethos_get_person",
                "referenceTaskName": "ethos_ref",
                "status": "FAILED",
                "startTime": 1700000000000,
                "endTime": 1700000010000,
                "retryCount": 2,
                "reasonForIncompletion": "HTTP 404 Not Found",
                "outputData": {},
            }
        ],
    }
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/reconciler/failures/wf-fail-001")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["workflowId"] == "wf-fail-001"
    assert data["failedTask"] is not None
    assert data["failedTask"]["errorCode"] == "HTTP_404"
    assert data["sisId"] == "SIS123"


# ---------------------------------------------------------------------------
# Bulk retry tests
# ---------------------------------------------------------------------------

def test_bulk_retry_calls_conductor(client):
    mock = _make_mock_conductor_with_failures()
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.post(
            "/api/v1/reconciler/failures/bulk-retry",
            json={"workflow_ids": ["wf-001", "wf-002", "wf-003"]},
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["retried"] == 3
    assert data["errors"] == []
    assert mock.retry_workflow.call_count == 3


def test_bulk_retry_empty_list_returns_error(client):
    mock = _make_mock_conductor_with_failures()
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.post(
            "/api/v1/reconciler/failures/bulk-retry",
            json={"workflow_ids": []},
            content_type="application/json",
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_bulk_retry_too_many_returns_error(client):
    mock = _make_mock_conductor_with_failures()
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.post(
            "/api/v1/reconciler/failures/bulk-retry",
            json={"workflow_ids": ["wf-" + str(i) for i in range(501)]},
            content_type="application/json",
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# Summary endpoint tests
# ---------------------------------------------------------------------------

def test_summary_endpoint(client):
    mock = _make_mock_conductor_with_failures()
    mock.list_workflow_definitions.return_value = [
        {"name": "student_enrollment", "version": 1},
        {"name": "financial_aid_processing", "version": 1},
    ]
    mock.get_failures_by_task_type.return_value = {
        "groups": [
            {"task_type": "ethos_get_person", "count": 3, "reasons": {"HTTP_404": 3}, "workflow_ids": []},
        ],
        "total_failures": 3,
    }
    with patch("app.routes.reconciler.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/reconciler/summary?hours_back=24")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data
    assert "total_failed" in data
    assert data["hours_back"] == 24
