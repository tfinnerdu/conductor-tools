"""Health check endpoints.

GET /api/v1/health      — liveness, always 200. Process-alive signal only.
                          Safe for Pingdom / Uptime Kuma at 30s cadence.
                          No dependency calls, no DB writes, no audit emissions.

GET /api/v1/health/deep — readiness with dependency probes. DB + Conductor.
                          Returns 200 (all ok), 200 with status=degraded
                          (non-critical dep slow), or 503 (critical dep down).
                          Intended for CI gates and admin diagnostics — not polling.

GET /health             — 308 redirect to /api/v1/health (transition shim).
GET /health/deep        — 308 redirect to /api/v1/health/deep (transition shim).
"""
import time
import uuid

from flask import Blueprint, current_app, jsonify, redirect

from app.health_checks import functional_checks
from app.utils.env import show_mock

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/v1/health")
def health():
    """Liveness — always 200 as long as the process is alive."""
    start_time = current_app.config.get("START_TIME", time.time())
    uptime = int(time.time() - start_time)

    return jsonify({
        "status": "ok",
        "service": "conductor-companion",
        "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
        "uptime_seconds": uptime,
    }), 200


@health_bp.route("/api/v1/health/deep")
def health_deep():
    """Readiness — DB + Conductor probes. CI gates and admin use only."""
    start_time = current_app.config.get("START_TIME", time.time())
    uptime = int(time.time() - start_time)
    request_id = str(uuid.uuid4())

    mock = show_mock()
    checks = functional_checks()
    status = "ok" if checks["ok"] else "degraded"

    current_app.logger.info(
        "health_check_deep",
        extra={
            "type": "functional",
            "request_id": request_id,
            "status": status,
            "mock": mock,
            "checks": {k: v["ok"] for k, v in checks["checks"].items()},
        },
    )

    return jsonify({
        "status": status,
        "service": "conductor-companion",
        "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
        "uptime_seconds": uptime,
        "mock": mock,
        "request_id": request_id,
        "checks": checks["checks"],
    }), (200 if checks["ok"] else 503)


# ---------------------------------------------------------------------------
# Transition shims — 308 redirects from bare /health paths (deprecated)
# ---------------------------------------------------------------------------

@health_bp.route("/health")
def health_redirect():
    return redirect("/api/v1/health", code=308)


@health_bp.route("/health/deep")
def health_deep_redirect():
    return redirect("/api/v1/health/deep", code=308)
