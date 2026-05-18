"""Ethos Integration Provider

Follows Doane *_provider.py pattern:
  _configured()  — env-gate (ETHOS_URL + ETHOS_API_KEY required)
  Real path      — calls Ethos REST API
  Mock fallback  — returns realistic Doane Ethos fixture data
  TODO markers   — every guessed field name flagged with # TODO(ethos):

Identity translation via resolve_identity() at the boundary.
"""
import os
import time
from collections import deque
from datetime import datetime, timezone

import requests

# In-memory ring buffer for incoming Ethos change events
# Shared with the Correlation Tracer — both apps read/write this buffer.
# In production, replace with a shared DB table (ethos_events).
_event_buffer: deque = deque(maxlen=500)


def _configured() -> bool:
    """Return True when Ethos credentials are present in environment."""
    return bool(os.environ.get("ETHOS_URL") and os.environ.get("ETHOS_API_KEY"))


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ.get('ETHOS_API_KEY', '')}",
        "Accept": "application/json",
    }


def resolve_identity(platform_user_id: str, source: str = "sis_id") -> str:
    """Single identity translation helper — all providers call this.

    Translates a platform user ID to the source system ID.
    In mock mode returns the input unchanged.
    # TODO(ethos): implement GUID <-> SIS_ID cross-lookup via ldm_guid table
    """
    return platform_user_id


def get_person(guid: str) -> dict:
    """Fetch a person record from Ethos by GUID.

    Real path: GET {ETHOS_URL}/api/persons/{guid}
    Returns Ethos EEDM persons v16 shape.
    """
    if not _configured():
        return _mock_person(guid)

    try:
        resp = requests.get(
            f"{os.environ['ETHOS_URL']}/api/persons/{guid}",
            headers=_get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return _mock_person(guid)


def get_recent_events(resource: str = "persons", limit: int = 50) -> list:
    """Return recent bus events for a resource type from the in-memory buffer.

    Real path: reads from _event_buffer (populated by ingest_event webhook).
    In production, query the ethos_events DB table instead.
    # TODO(ethos): replace with DB query once ethos_events table is live
    """
    events = [e for e in _event_buffer if e.get("resource") == resource]
    return events[-limit:]


def ingest_event(event: dict) -> None:
    """Ingest an Ethos change notification event into the buffer.

    Called by the /api/v1/ethos/events POST webhook when Ethos publishes
    a change notification. Thread-safe deque append.
    """
    event["received_at"] = datetime.now(timezone.utc).isoformat()
    _event_buffer.append(event)


def search_persons(query: str, limit: int = 20) -> list:
    """Search Ethos for persons matching a query string.

    Real path: GET {ETHOS_URL}/api/persons?criteria={...}
    # TODO(ethos): confirm criteria param name and JSON filter shape
    """
    if not _configured():
        return _mock_person_search(query, limit)

    try:
        resp = requests.get(
            f"{os.environ['ETHOS_URL']}/api/persons",
            headers=_get_headers(),
            params={"criteria": query, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return _mock_person_search(query, limit)


def check_health() -> dict:
    """Probe Ethos API availability.  Read-only, safe for health checks."""
    if not _configured():
        return {"ok": True, "detail": "not_configured", "latency_ms": None}

    t0 = time.time()
    try:
        resp = requests.get(
            f"{os.environ['ETHOS_URL']}/api/about",  # TODO(ethos): confirm health endpoint path
            headers=_get_headers(),
            timeout=3,
        )
        latency_ms = round((time.time() - t0) * 1000)
        return {
            "ok": resp.status_code < 500,
            "latency_ms": latency_ms,
            "detail": "reachable" if resp.status_code < 500 else f"http_{resp.status_code}",
        }
    except requests.Timeout:
        return {"ok": False, "latency_ms": round((time.time() - t0) * 1000), "detail": "timeout"}
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.time() - t0) * 1000), "detail": str(exc)[:120]}


# ---------------------------------------------------------------------------
# Mock fixtures — realistic Doane Ethos EEDM shapes
# ---------------------------------------------------------------------------

def _mock_person(guid: str) -> dict:
    return {
        "id": guid,  # TODO(ethos): confirm top-level GUID field name
        "content": {
            "names": [  # TODO(ethos): confirm names array structure
                {
                    "firstName": "Alex",
                    "lastName": "Student",
                    "fullName": "Alex Student",
                    "preference": "preferred",
                }
            ],
            "credentials": [  # TODO(ethos): confirm credentials array structure
                {"type": {"credentialType": "colleaguePersonId"}, "value": "STU" + guid[-6:].upper().replace("-", "0")},  # TODO(ethos): confirm credentialType enum value
            ],
            "emails": [  # TODO(ethos): confirm emails array structure
                {"address": "alex.student@doane.edu", "preference": "primary"},  # TODO(ethos): confirm preference enum
            ],
            "phones": [],
        },
        "resource": "persons",
        "operation": "updated",  # TODO(ethos): confirm operation field name
    }


def _mock_person_search(query: str, limit: int) -> list:
    return [_mock_person(f"mock-guid-{i:04d}") for i in range(min(limit, 5))]
