"""Shared health check functions — imported by both the health route and tests.

Two classes of checks per Doane Health Endpoint Discipline:

  read_only_checks()  — safe for Pingdom/Uptime Kuma at 30s cadence.
                        No DB writes, no audit emissions, no cache writes.
                        Lightweight HTTP probe to Conductor /health if configured.

  functional_checks() — exercises real code paths: DB round-trip + Conductor
                        API call. CI gates and admin diagnostics only. Never
                        wire to automated polling.
"""
import os
import time

import requests

# Module-level imports so tests can patch app.health_checks.db and
# app.health_checks.ConductorClient directly without chasing lazy imports.
from app import db
from app.conductor_client import ConductorClient
from app.utils.env import show_mock


def check_conductor_live() -> dict:
    """Lightweight probe: GET CONDUCTOR_URL/health with a 2s timeout.

    Safe for frequent polling — read-only, no side effects.
    Returns {ok, latency_ms, detail}.
    """
    if show_mock():
        return {"ok": True, "detail": "mock_mode", "latency_ms": None}

    base_url = os.environ.get("CONDUCTOR_URL", "").rstrip("/")
    if not base_url:
        return {"ok": False, "detail": "not_configured", "latency_ms": None}

    api_key = os.environ.get("CONDUCTOR_API_KEY")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Authorization"] = api_key

    t0 = time.time()
    try:
        resp = requests.get(f"{base_url}/health", headers=headers, timeout=2)
        latency_ms = round((time.time() - t0) * 1000)
        if resp.status_code < 500:
            return {"ok": True, "latency_ms": latency_ms, "detail": "reachable"}
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "detail": f"http_{resp.status_code}",
        }
    except requests.Timeout:
        latency_ms = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "detail": "timeout"}
    except Exception as exc:
        latency_ms = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "detail": str(exc)[:120]}


def check_db() -> dict:
    """Functional DB check: execute SELECT 1 against the configured database.

    CI/deep-check only — not safe for high-frequency polling.
    Returns {ok, latency_ms, detail}.
    """
    t0 = time.time()
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        latency_ms = round((time.time() - t0) * 1000)
        return {"ok": True, "latency_ms": latency_ms, "detail": "connected"}
    except Exception as exc:
        latency_ms = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "detail": str(exc)[:120]}


def check_conductor_functional() -> dict:
    """Functional Conductor check: fetch workflow definitions (real API call).

    CI/deep-check only. With SHOW_MOCK enabled, returns ok=True without
    hitting the network. Otherwise Conductor is a critical dependency — when
    CONDUCTOR_URL is not configured this reports ok=False so
    /api/v1/health/deep returns 503.
    Returns {ok, latency_ms, detail, workflow_count?}.
    """
    if show_mock():
        return {"ok": True, "detail": "mock_mode", "latency_ms": None}

    base_url = os.environ.get("CONDUCTOR_URL", "").rstrip("/")
    if not base_url:
        return {"ok": False, "detail": "not_configured", "latency_ms": None}

    t0 = time.time()
    try:
        client = ConductorClient()
        defs = client.list_workflow_definitions()
        latency_ms = round((time.time() - t0) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "detail": "reachable",
            "workflow_count": len(defs),
        }
    except Exception as exc:
        latency_ms = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "detail": str(exc)[:120]}


def read_only_checks() -> dict:
    """Run all read-only health checks. Safe for Pingdom at 30s cadence."""
    conductor = check_conductor_live()
    all_ok = conductor["ok"]
    return {
        "ok": all_ok,
        "checks": {
            "conductor": conductor,
        },
    }


def functional_checks() -> dict:
    """Run all functional health checks. CI gates and admin diagnostics only."""
    db_result = check_db()
    conductor_result = check_conductor_functional()
    all_ok = db_result["ok"] and conductor_result["ok"]
    return {
        "ok": all_ok,
        "checks": {
            "db": db_result,
            "conductor": conductor_result,
        },
    }
