"""Health check endpoints.

GET /health       — read-only, live-safe. Uptime + lightweight Conductor probe.
                    Safe for Pingdom / Uptime Kuma at 30s cadence.

GET /health/deep  — functional / CI-only. DB round-trip + real Conductor API call.
                    Never wire to automated polling.
"""
import time
import uuid

from flask import Blueprint, current_app, jsonify

from app.health_checks import functional_checks, read_only_checks

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Read-only health check — safe for high-frequency monitoring."""
    start_time = current_app.config.get("START_TIME", time.time())
    uptime = round(time.time() - start_time, 1)

    checks = read_only_checks()
    status = "ok" if checks["ok"] else "degraded"

    current_app.logger.info(
        "health_check",
        extra={"type": "live", "status": status, "uptime_seconds": uptime},
    )

    return jsonify(
        {
            "status": status,
            "service": "conductor-companion",
            "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
            "uptime_seconds": uptime,
            "checks": checks["checks"],
        }
    ), (200 if checks["ok"] else 503)


@health_bp.route("/health/deep")
def health_deep():
    """Functional health check — DB + Conductor API. CI gates and admin use only."""
    start_time = current_app.config.get("START_TIME", time.time())
    uptime = round(time.time() - start_time, 1)
    request_id = str(uuid.uuid4())

    checks = functional_checks()
    status = "ok" if checks["ok"] else "degraded"

    # One audit emission per request — never one per fan-out item.
    current_app.logger.info(
        "health_check_deep",
        extra={
            "type": "functional",
            "request_id": request_id,
            "status": status,
            "checks": {k: v["ok"] for k, v in checks["checks"].items()},
        },
    )

    return jsonify(
        {
            "status": status,
            "service": "conductor-companion",
            "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
            "uptime_seconds": uptime,
            "request_id": request_id,
            "checks": checks["checks"],
        }
    ), (200 if checks["ok"] else 503)
