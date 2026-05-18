"""Health check endpoint."""
import time

from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Return service health status."""
    start_time = current_app.config.get("START_TIME", time.time())
    uptime = round(time.time() - start_time, 1)
    return jsonify(
        {
            "status": "ok",
            "service": "conductor-companion",
            "version": current_app.config.get("SERVICE_VERSION", "1.0.0"),
            "uptime_seconds": uptime,
        }
    )
