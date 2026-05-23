"""Ethos Integration Provider

  _configured()  — env-gate (ETHOS_URL + ETHOS_API_KEY required)
  Real path      — calls the Ethos REST API
  TODO markers   — every guessed field name flagged with # TODO(ethos):

By default this provider makes real Ethos calls — if credentials are not
configured, calls raise RuntimeError. Setting SHOW_MOCK=1 in the environment
flips reads to return realistic mock fixtures instead, for offline testing.
SHOW_MOCK is an EXPLICIT, opt-in flag — never an error-recovery path.

Identity translation via resolve_identity() at the boundary.
"""
import os
import time
from collections import deque
from datetime import datetime, timezone

import requests

from app.utils.env import show_mock

# In-memory ring buffer for incoming Ethos change events.
# Shared with the Correlation Tracer — both apps read/write this buffer.
# In production, replace with a shared DB table (ethos_events).
_event_buffer: deque = deque(maxlen=500)


def _configured() -> bool:
    return bool(os.environ.get("ETHOS_URL") and os.environ.get("ETHOS_API_KEY"))


def _require_configured() -> None:
    if not _configured():
        raise RuntimeError(
            "Ethos is not configured — set ETHOS_URL and ETHOS_API_KEY, "
            "or enable SHOW_MOCK for fixture data."
        )


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ.get('ETHOS_API_KEY', '')}",
        "Accept": "application/json",
    }


def resolve_identity(platform_user_id: str, source: str = "sis_id") -> str:
    """Single identity translation helper — all providers call this.

    # TODO(ethos): implement GUID <-> SIS_ID cross-lookup via ldm_guid table
    """
    return platform_user_id


def get_person(guid: str) -> dict:
    """Fetch a person record from Ethos by GUID.

    Real path: GET {ETHOS_URL}/api/persons/{guid}
    Returns Ethos EEDM persons v16 shape.
    """
    if show_mock():
        return _mock_person(guid)
    _require_configured()
    resp = requests.get(
        f"{os.environ['ETHOS_URL']}/api/persons/{guid}",
        headers=_get_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_recent_events(resource: str = "persons", limit: int = 50) -> list:
    """Return recent bus events for a resource type from the in-memory buffer.

    The buffer is populated by the ingest_event webhook — real captured data,
    not fixtures, so SHOW_MOCK is irrelevant here.
    # TODO(ethos): replace with DB query once ethos_events table is live
    """
    events = [e for e in _event_buffer if e.get("resource") == resource]
    return events[-limit:]


def ingest_event(event: dict) -> None:
    """Ingest an Ethos change notification event into the buffer."""
    event["received_at"] = datetime.now(timezone.utc).isoformat()
    _event_buffer.append(event)


def search_persons(query: str, limit: int = 20) -> list:
    """Search Ethos for persons matching a query string.

    # TODO(ethos): confirm criteria param name and JSON filter shape
    """
    if show_mock():
        return _mock_person_search(query, limit)
    _require_configured()
    resp = requests.get(
        f"{os.environ['ETHOS_URL']}/api/persons",
        headers=_get_headers(),
        params={"criteria": query, "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


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
# Mock fixtures — used only when SHOW_MOCK is enabled
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
                {"type": {"credentialType": "colleaguePersonId"}, "value": "STU" + guid[-6:].upper().replace("-", "0")},
            ],
            "emails": [  # TODO(ethos): confirm emails array structure
                {"address": "alex.student@doane.edu", "preference": "primary"},
            ],
            "phones": [],
        },
        "resource": "persons",
        "operation": "updated",
    }


def _mock_person_search(query: str, limit: int) -> list:
    return [_mock_person(f"mock-guid-{i:04d}") for i in range(min(limit, 5))]
