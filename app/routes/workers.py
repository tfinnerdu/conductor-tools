"""Workers routes — /api/v1/workers/*"""
import time

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient
from app.utils.responses import error_response

workers_bp = Blueprint("workers", __name__, url_prefix="/api/v1/workers")


def _classify_worker(seconds_since_poll: float) -> str:
    """Classify a worker based on seconds since last poll.

    healthy    - last polled within 5 seconds
    slow_poll  - last polled 5–30 seconds ago
    down       - last polled 30+ seconds ago
    """
    if seconds_since_poll < 5:
        return "healthy"
    elif seconds_since_poll < 30:
        return "slow_poll"
    else:
        return "down"


def _classify_task_type(worker_records: list, queue_size: int) -> dict:
    """Compute aggregate health classification for a task type."""
    now_ms = int(time.time() * 1000)

    if not worker_records:
        return {
            "workerCount": 0,
            "status": "no_workers",
            "lastPollAgoSeconds": None,
            "workerIds": [],
            "queueDepth": queue_size,
        }

    worker_ids = []
    last_poll_ms = 0
    for record in worker_records:
        wid = record.get("workerId", record.get("workerId", "unknown"))
        worker_ids.append(wid)
        lpt = record.get("lastPollTime", 0)
        if lpt > last_poll_ms:
            last_poll_ms = lpt

    seconds_since_poll = (now_ms - last_poll_ms) / 1000.0 if last_poll_ms else 9999
    status = _classify_worker(seconds_since_poll)

    return {
        "workerCount": len(worker_ids),
        "status": status,
        "lastPollAgoSeconds": round(seconds_since_poll, 1),
        "workerIds": worker_ids,
        "queueDepth": queue_size,
    }


@workers_bp.route("/status", methods=["GET"])
def worker_status():
    """Return worker registry with health classification for all task types."""
    try:
        client = ConductorClient()
        all_queues = client.get_all_task_queues()

        registry = []
        for task_type, queue_data in all_queues.items():
            queue_size = queue_data.get("queueSize", 0)
            worker_details = queue_data.get("workerDetails", {})

            # workerDetails is a dict keyed by workerId with poll info
            worker_records = []
            for worker_id, details in worker_details.items():
                worker_records.append({
                    "workerId": worker_id,
                    "lastPollTime": details.get("lastPollTime", 0),
                })

            classification = _classify_task_type(worker_records, queue_size)
            registry.append({
                "taskType": task_type,
                **classification,
            })

        # Sort: down/no_workers first, then slow_poll, then healthy
        status_order = {"no_workers": 0, "down": 1, "slow_poll": 2, "healthy": 3}
        registry.sort(key=lambda r: status_order.get(r["status"], 99))

        return jsonify({
            "workers": registry,
            "totalTaskTypes": len(registry),
            "summaryCounts": {
                s: sum(1 for r in registry if r["status"] == s)
                for s in ("healthy", "slow_poll", "down", "no_workers")
            },
            "refreshedAt": int(time.time()),
        })
    except Exception as exc:
        current_app.logger.error("worker_status error: %s", exc, exc_info=True)
        return error_response(str(exc), "WORKER_STATUS_ERROR", 500)


@workers_bp.route("/<task_type>/performance", methods=["GET"])
def worker_performance(task_type: str):
    """Return task-level performance stats for a given task type."""
    try:
        client = ConductorClient()
        perf = client.get_task_performance(task_type)
        return jsonify(perf)
    except Exception as exc:
        current_app.logger.error("worker_performance error: %s", exc, exc_info=True)
        return error_response(str(exc), "PERF_ERROR", 500)
