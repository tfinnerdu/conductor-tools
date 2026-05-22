"""Tests for the Workflow Test Harness routes."""
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_conductor_th():
    mock = MagicMock()
    mock.base_url = "http://conductor.test"
    mock.get_headers.return_value = {}

    mock.list_workflow_definitions.return_value = [
        {"name": "student_enrollment", "version": 1, "description": "Student enrollment"},
        {"name": "student_enrollment", "version": 2, "description": "Student enrollment v2"},
        {"name": "financial_aid_processing", "version": 1, "description": "Financial aid"},
        {"name": "order_fulfillment", "version": 1, "description": "Order fulfillment"},
    ]

    mock.get_workflow_definition.return_value = {
        "name": "student_enrollment",
        "version": 1,
        "description": "Student enrollment",
        "tasks": [
            {
                "name": "ethos_get_person",
                "taskReferenceName": "ethos_get_person_ref",
                "type": "SIMPLE",
                "inputParameters": {"guid": "${workflow.input.guid}"},
            },
            {
                "name": "enroll_student",
                "taskReferenceName": "enroll_ref",
                "type": "SIMPLE",
                "inputParameters": {"sis_id": "${workflow.input.sis_id}"},
            },
        ],
        "outputParameters": {},
    }

    return mock


# ---------------------------------------------------------------------------
# GET /workflows
# ---------------------------------------------------------------------------

def test_list_workflows(client):
    mock = _make_mock_conductor_th()
    with patch("app.routes.test_harness.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/test-harness/workflows")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "workflows" in data
    workflows = data["workflows"]
    assert len(workflows) >= 1
    for wf in workflows:
        assert "name" in wf
        assert "version" in wf


# ---------------------------------------------------------------------------
# GET /workflows/<name>/tasks
# ---------------------------------------------------------------------------

def test_get_workflow_tasks_returns_refs(client):
    mock = _make_mock_conductor_th()
    with patch("app.routes.test_harness.ConductorClient", return_value=mock):
        resp = client.get("/api/v1/test-harness/workflows/student_enrollment/tasks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tasks" in data
    tasks = data["tasks"]
    assert len(tasks) == 2

    ref_names = [t["ref_name"] for t in tasks]
    assert "ethos_get_person_ref" in ref_names
    assert "enroll_ref" in ref_names

    for t in tasks:
        assert "ref_name" in t
        assert "task_type" in t
        assert "task_name" in t


# ---------------------------------------------------------------------------
# POST /run — posts to Conductor's workflow test endpoint
# ---------------------------------------------------------------------------

def test_run_posts_to_conductor_test_endpoint(client):
    """run_test POSTs to Conductor's /api/workflow/test and returns the result."""
    mock = _make_mock_conductor_th()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "workflowId": "test-run-001",
        "status": "COMPLETED",
        "tasks": [{"referenceTaskName": "enroll_ref", "status": "COMPLETED"}],
    }
    with patch("app.routes.test_harness.ConductorClient", return_value=mock), \
         patch("app.routes.test_harness.requests.post", return_value=mock_resp) as mock_post:
        resp = client.post(
            "/api/v1/test-harness/run",
            json={
                "workflow_name": "student_enrollment",
                "version": 1,
                "input": {"sis_id": "SIS123456", "guid": "11111111-1111-1111-1111-111111111111"},
                "task_mocks": {
                    "enroll_ref": {"outputData": {"enrolled": True, "enrollmentId": "ENR-001"}},
                },
            },
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["workflowId"] == "test-run-001"
    assert data["status"] == "COMPLETED"
    assert isinstance(data["tasks"], list)
    # Must hit Conductor's workflow test endpoint
    assert mock_post.call_args[0][0] == "http://conductor.test/api/workflow/test"


def test_run_missing_workflow_name_returns_error(client):
    mock = _make_mock_conductor_th()
    with patch("app.routes.test_harness.ConductorClient", return_value=mock):
        resp = client.post(
            "/api/v1/test-harness/run",
            json={"input": {}, "task_mocks": {}},
            content_type="application/json",
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "VALIDATION_ERROR"


def test_run_surfaces_failed_result_from_conductor(client):
    """A FAILED result from Conductor's test endpoint is surfaced unchanged."""
    mock = _make_mock_conductor_th()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "workflowId": "test-run-002",
        "status": "FAILED",
        "tasks": [{
            "referenceTaskName": "ethos_get_person_ref",
            "status": "FAILED",
            "reasonForIncompletion": "Person not found",
        }],
    }
    with patch("app.routes.test_harness.ConductorClient", return_value=mock), \
         patch("app.routes.test_harness.requests.post", return_value=mock_resp):
        resp = client.post(
            "/api/v1/test-harness/run",
            json={
                "workflow_name": "student_enrollment",
                "version": 1,
                "input": {"sis_id": "SIS_NOTFOUND"},
                "task_mocks": {},
            },
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "FAILED"
    failed_tasks = [t for t in data["tasks"] if t["status"] == "FAILED"]
    assert len(failed_tasks) >= 1


# ---------------------------------------------------------------------------
# GET /presets
# ---------------------------------------------------------------------------

def test_get_presets_returns_four_builtins(client):
    resp = client.get("/api/v1/test-harness/presets")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "presets" in data
    presets = data["presets"]
    # Should contain at least the 4 built-in presets
    assert len(presets) >= 4
    builtin_names = [p["name"] for p in presets if p.get("builtin")]
    assert "Person created in Colleague" in builtin_names
    assert "Person address updated" in builtin_names
    assert "Application submitted" in builtin_names
    assert "Ethos 404 error" in builtin_names


def test_get_presets_returns_preset_shape(client):
    resp = client.get("/api/v1/test-harness/presets")
    data = resp.get_json()
    for preset in data["presets"]:
        assert "name" in preset
        assert "workflowName" in preset
        assert "input" in preset
        assert "taskMocks" in preset


# ---------------------------------------------------------------------------
# POST /presets
# ---------------------------------------------------------------------------

def test_save_preset(client):
    resp = client.post(
        "/api/v1/test-harness/presets",
        json={
            "name": "My Custom Preset",
            "description": "Test preset",
            "workflow_name": "student_enrollment",
            "input": {"sis_id": "SIS999"},
            "task_mocks": {"enroll_ref": {"outputData": {"enrolled": True}}},
            "created_by": "tester",
        },
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "My Custom Preset"
    assert data["id"] is not None


def test_save_preset_missing_name_returns_error(client):
    resp = client.post(
        "/api/v1/test-harness/presets",
        json={"workflow_name": "student_enrollment"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "VALIDATION_ERROR"
