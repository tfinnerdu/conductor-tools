"""Tests for the Correlation Tracer routes and helpers."""
import time
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# diagnose_sf_state tests
# ---------------------------------------------------------------------------

def test_diagnose_sf_state_no_records():
    from app.routes.tracer import diagnose_sf_state
    result = diagnose_sf_state([])
    assert "not found" in result.lower() or "failed" in result.lower()


def test_diagnose_sf_state_duplicate():
    from app.routes.tracer import diagnose_sf_state
    records = [
        {"Id": "SF001", "SIS_ID__c": "SIS123"},
        {"Id": "SF002", "SIS_ID__c": "SIS123"},
    ]
    result = diagnose_sf_state(records)
    assert "DUPLICATE" in result.upper()
    assert "2" in result


def test_diagnose_sf_state_missing_sis_id():
    from app.routes.tracer import diagnose_sf_state
    records = [{"Id": "SF003", "SIS_ID__c": None}]
    result = diagnose_sf_state(records)
    assert "missing" in result.lower() or "SIS_ID__c" in result


def test_diagnose_sf_state_healthy():
    from app.routes.tracer import diagnose_sf_state
    records = [{"Id": "SF004", "SIS_ID__c": "SIS999", "FirstName": "Alex"}]
    result = diagnose_sf_state(records)
    assert "healthy" in result.lower()


# ---------------------------------------------------------------------------
# Tracer POST /person endpoint tests
# ---------------------------------------------------------------------------

def _make_mock_conductor_tracer():
    mock = MagicMock()
    now_ms = int(time.time() * 1000)
    mock.search.return_value = {
        "totalHits": 2,
        "results": [
            {
                "workflowId": "trace-wf-001",
                "workflowType": "student_enrollment",
                "status": "COMPLETED",
                "startTime": now_ms - 3600000,
                "endTime": now_ms - 3500000,
                "correlationId": "11111111-1111-1111-1111-111111111111",
            },
            {
                "workflowId": "trace-wf-002",
                "workflowType": "financial_aid_processing",
                "status": "FAILED",
                "startTime": now_ms - 7200000,
                "endTime": now_ms - 7100000,
                "correlationId": "11111111-1111-1111-1111-111111111111",
            },
        ],
    }
    return mock


def _mock_sf_provider():
    """A MagicMock sf_provider returning a real result dict (the provider now
    raises RuntimeError unless Salesforce is configured)."""
    mock = MagicMock()
    sf_result = {
        "records": [{"Id": "SF001", "FirstName": "Alex", "LastName": "Student",
                     "SIS_ID__c": "SIS123456",
                     "Ethos_Guid__c": "11111111-1111-1111-1111-111111111111"}],
        "record_count": 1,
        "status": "ok",
        "diagnosis": "Record looks healthy",
    }
    mock.find_person_by_sis_id.return_value = sf_result
    mock.find_person_by_guid.return_value = sf_result
    return mock


def test_trace_by_guid_returns_timeline(client):
    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock), \
         patch("app.routes.tracer.sf_provider", _mock_sf_provider()):
        resp = client.post(
            "/api/v1/tracer/person",
            json={"guid": "11111111-1111-1111-1111-111111111111", "sis_id": ""},
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "trace" in data
    assert isinstance(data["trace"], list)
    assert len(data["trace"]) > 0
    assert data["guid"] == "11111111-1111-1111-1111-111111111111"
    assert "diagnosis" in data

    # Check timeline events have required fields
    for event in data["trace"]:
        assert "timestamp" in event
        assert "system" in event
        assert "event" in event
        assert "status" in event


def test_trace_by_sis_id_returns_timeline(client):
    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock), \
         patch("app.routes.tracer.sf_provider", _mock_sf_provider()):
        resp = client.post(
            "/api/v1/tracer/person",
            json={"guid": "", "sis_id": "SIS123456"},
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "trace" in data
    assert data["sis_id"] == "SIS123456"
    # Should have at least a Salesforce event
    systems = {ev["system"] for ev in data["trace"]}
    assert "SALESFORCE" in systems


def test_trace_missing_identifier_returns_error(client):
    with patch("app.routes.tracer.ConductorClient", return_value=MagicMock()):
        resp = client.post(
            "/api/v1/tracer/person",
            json={},
            content_type="application/json",
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert data["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Recent traces buffer
# ---------------------------------------------------------------------------

def test_recent_traces_buffer(client):
    from app.routes.tracer import _recent_traces

    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock):
        # Perform a trace to populate the buffer
        client.post(
            "/api/v1/tracer/person",
            json={"guid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
            content_type="application/json",
        )

    resp = client.get("/api/v1/tracer/recent")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "recent" in data
    assert isinstance(data["recent"], list)


def test_recent_traces_buffer_capped_at_20(client):
    from app.routes.tracer import _recent_traces

    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock):
        for i in range(25):
            guid = f"bbbbbbbb-{i:04d}-bbbb-bbbb-bbbbbbbbbbbb"
            client.post(
                "/api/v1/tracer/person",
                json={"guid": guid},
                content_type="application/json",
            )

    assert len(_recent_traces) <= 20


# ---------------------------------------------------------------------------
# GET /person/<identifier> shorthand
# ---------------------------------------------------------------------------

def test_trace_get_with_guid(client):
    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock), \
         patch("app.routes.tracer.sf_provider", _mock_sf_provider()):
        resp = client.get("/api/v1/tracer/person/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["guid"] == "11111111-1111-1111-1111-111111111111"
    assert data["sis_id"] is None


def test_trace_get_with_sis_id(client):
    mock = _make_mock_conductor_tracer()
    with patch("app.routes.tracer.ConductorClient", return_value=mock), \
         patch("app.routes.tracer.sf_provider", _mock_sf_provider()):
        resp = client.get("/api/v1/tracer/person/SIS123456")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sis_id"] == "SIS123456"
    assert data["guid"] is None
