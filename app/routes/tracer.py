"""Tracer routes — /api/v1/tracer/*

End-to-End Correlation Tracer: given a GUID or SIS_ID, produces a unified
timeline of events across Conductor (real) and Salesforce (mock).
"""
import re
import uuid
from collections import deque
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient

tracer_bp = Blueprint("tracer", __name__, url_prefix="/api/v1/tracer")

# In-memory ring buffer for recent trace searches (thread-safe appends only)
_recent_traces: deque = deque(maxlen=20)

# Pattern for detecting UUID-format GUIDs
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


def _is_guid(identifier: str) -> bool:
    """Return True if identifier looks like a UUID/GUID."""
    return bool(_UUID_RE.match(identifier.strip()))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def diagnose_sf_state(records: list) -> str:
    """Produce a human-readable diagnosis of a Salesforce record state."""
    count = len(records)
    if count == 0:
        return "Record not found in Salesforce — migration has not run or failed"
    if count > 1:
        return f"DUPLICATE: {count} records found — merge required"
    record = records[0]
    if not record.get("SIS_ID__c"):
        return "Record exists but missing SIS_ID__c"
    return "Record looks healthy"


def _mock_sf_lookup(identifier: str, search_type: str) -> dict:
    """Return mock Salesforce data shaped like a real SF query result."""
    # Simulate: most identifiers find exactly one healthy record
    # A few edge cases are seeded for testing
    if "dup" in identifier.lower():
        records = [
            {"Id": "SF001", "FirstName": "Jane", "LastName": "Doe", "SIS_ID__c": identifier},
            {"Id": "SF002", "FirstName": "Jane", "LastName": "Doe", "SIS_ID__c": identifier},
        ]
    elif "missing" in identifier.lower():
        records = [{"Id": "SF003", "FirstName": "John", "LastName": "Smith", "SIS_ID__c": None}]
    elif "notfound" in identifier.lower() or "404" in identifier:
        records = []
    else:
        records = [
            {
                "Id": "SF" + identifier[-6:].upper().replace("-", "0"),
                "FirstName": "Alex",
                "LastName": "Student",
                "SIS_ID__c": identifier,
                "Email": "alex.student@doane.edu",
                "RecordType": "Person",
            }
        ]

    diagnosis = diagnose_sf_state(records)
    status = "ok"
    if len(records) == 0:
        status = "error"
    elif len(records) > 1 or (len(records) == 1 and not records[0].get("SIS_ID__c")):
        status = "warning"

    return {
        "records": records,
        "record_count": len(records),
        "status": status,
        "diagnosis": diagnosis,
    }


def _build_timeline(conductor_results: list, sf_result: dict, identifier: str) -> list:
    """Merge Conductor executions and SF data into a sorted timeline."""
    events = []

    # Add Conductor events
    for exec_summary in conductor_results:
        wf_id = exec_summary.get("workflowId", "unknown")
        wf_type = exec_summary.get("workflowType", "unknown")
        status = exec_summary.get("status", "UNKNOWN")
        start_ms = exec_summary.get("startTime")
        end_ms = exec_summary.get("endTime")

        if start_ms:
            ts = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat()
        else:
            ts = _now_iso()

        events.append(
            {
                "timestamp": ts,
                "system": "CONDUCTOR",
                "event": f"Workflow started: {wf_type}",
                "detail": f"workflowId={wf_id}",
                "status": "running" if status == "RUNNING" else "ok" if status == "COMPLETED" else "error",
                "workflowId": wf_id,
                "workflowType": wf_type,
                "workflowStatus": status,
            }
        )

        if end_ms and status != "RUNNING":
            ts_end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).isoformat()
            events.append(
                {
                    "timestamp": ts_end,
                    "system": "CONDUCTOR",
                    "event": f"Workflow {status.lower()}: {wf_type}",
                    "detail": f"workflowId={wf_id}",
                    "status": "ok" if status == "COMPLETED" else "error",
                    "workflowId": wf_id,
                    "workflowType": wf_type,
                    "workflowStatus": status,
                }
            )

    # Add Salesforce event
    sf_ts = _now_iso()
    sf_status = sf_result.get("status", "ok")
    events.append(
        {
            "timestamp": sf_ts,
            "system": "SALESFORCE",
            "event": "Salesforce record lookup",
            "detail": sf_result.get("diagnosis", ""),
            "status": sf_status,
            "records": sf_result.get("records", []),
            "record_count": sf_result.get("record_count", 0),
        }
    )

    # Sort ascending by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))
    return events


@tracer_bp.post("/person")
def trace_person():
    """Trace all events for a person identified by GUID and/or SIS_ID.

    Body: {"guid": "...", "sis_id": "..."}  (either or both)
    Returns: {trace: [...], guid, sis_id, diagnosis}
    """
    body = request.get_json(force=True) or {}
    guid = (body.get("guid") or "").strip()
    sis_id = (body.get("sis_id") or "").strip()

    if not guid and not sis_id:
        return _error("At least one of guid or sis_id is required", "VALIDATION_ERROR")

    identifier = guid or sis_id

    try:
        client = ConductorClient()

        # Search Conductor by free text for the identifier
        search_result = client.search(free_text=identifier)
        conductor_results = search_result.get("results", [])

        # Mock Salesforce lookup
        sf_result = _mock_sf_lookup(sis_id or guid, "sis_id" if sis_id else "guid")

        timeline = _build_timeline(conductor_results, sf_result, identifier)

        diagnosis = sf_result.get("diagnosis", "")
        had_errors = any(e.get("status") == "error" for e in timeline)
        error_events = [e for e in timeline if e.get("status") == "error"]
        if error_events:
            diagnosis = f"{len(error_events)} error(s) found in trace. " + diagnosis

        # Record in recent traces buffer
        _recent_traces.append(
            {
                "searched_at": _now_iso(),
                "guid": guid or None,
                "sis_id": sis_id or None,
                "event_count": len(timeline),
                "had_errors": had_errors,
            }
        )

        current_app.logger.info(
            "trace_person: identifier=%s conductor_hits=%d sf_records=%d",
            identifier,
            len(conductor_results),
            sf_result.get("record_count", 0),
        )

        return jsonify(
            {
                "trace": timeline,
                "guid": guid or None,
                "sis_id": sis_id or None,
                "diagnosis": diagnosis,
                "conductor_hits": len(conductor_results),
                "sf_record_count": sf_result.get("record_count", 0),
            }
        )
    except Exception as exc:
        current_app.logger.error("trace_person error: %s", exc, exc_info=True)
        return _error(str(exc), "TRACE_ERROR", 500)


@tracer_bp.get("/recent")
def recent_traces():
    """Return the last 20 trace searches from the in-memory ring buffer."""
    return jsonify({"recent": list(reversed(list(_recent_traces)))})


@tracer_bp.get("/person/<identifier>")
def trace_person_get(identifier: str):
    """GET shorthand — identifier is either a GUID or SIS_ID.

    UUID format (8-4-4-4-12 hex) is treated as a GUID; anything else as SIS_ID.
    """
    identifier = identifier.strip()
    if not identifier:
        return _error("identifier is required", "VALIDATION_ERROR")

    if _is_guid(identifier):
        body = {"guid": identifier, "sis_id": ""}
    else:
        body = {"guid": "", "sis_id": identifier}

    # Re-use the POST handler logic by pushing through a fake request context
    try:
        client = ConductorClient()
        search_result = client.search(free_text=identifier)
        conductor_results = search_result.get("results", [])

        sis_id = "" if _is_guid(identifier) else identifier
        sf_result = _mock_sf_lookup(sis_id or identifier, "sis_id" if sis_id else "guid")

        timeline = _build_timeline(conductor_results, sf_result, identifier)

        had_errors = any(e.get("status") == "error" for e in timeline)
        diagnosis = sf_result.get("diagnosis", "")

        _recent_traces.append(
            {
                "searched_at": _now_iso(),
                "guid": identifier if _is_guid(identifier) else None,
                "sis_id": identifier if not _is_guid(identifier) else None,
                "event_count": len(timeline),
                "had_errors": had_errors,
            }
        )

        current_app.logger.info(
            "trace_person_get: identifier=%s is_guid=%s conductor_hits=%d",
            identifier,
            _is_guid(identifier),
            len(conductor_results),
        )

        return jsonify(
            {
                "trace": timeline,
                "guid": identifier if _is_guid(identifier) else None,
                "sis_id": identifier if not _is_guid(identifier) else None,
                "diagnosis": diagnosis,
                "conductor_hits": len(conductor_results),
                "sf_record_count": sf_result.get("record_count", 0),
            }
        )
    except Exception as exc:
        current_app.logger.error("trace_person_get error: %s", exc, exc_info=True)
        return _error(str(exc), "TRACE_ERROR", 500)
