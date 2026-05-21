"""Digest routes — /api/v1/digest/*

Performance Digest: daily summaries of workflow activity, failure trends,
regressions, and worker health.  Uses APScheduler to cache results at 06:00
daily; falls back to on-demand generation if no cached result exists.
"""
from datetime import datetime, timezone, timedelta

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient
from app.utils.responses import error_response

digest_bp = Blueprint("digest", __name__, url_prefix="/api/v1/digest")

# ---------------------------------------------------------------------------
# In-memory cache (keyed by YYYY-MM-DD date string, holds last 7 entries)
# ---------------------------------------------------------------------------

_digest_cache: dict = {}  # {date_str: digest_dict}
_MAX_CACHE = 7


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _date_str(days_back: int = 0) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days_back)
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Digest generation logic
# ---------------------------------------------------------------------------

def _compute_workflow_stats(client: ConductorClient, wf_name: str, hours_back: int) -> dict:
    """Compute stats for a single workflow type using the search API."""
    result = client.search(
        workflow_type=wf_name,
        size=500,
    )
    executions = result.get("results", [])

    total = len(executions)
    failed = sum(1 for e in executions if e.get("status") == "FAILED")
    failure_rate = round((failed / total * 100) if total else 0, 1)

    durations = []
    for ex in executions:
        st = ex.get("startTime", 0)
        et = ex.get("endTime", 0)
        if st and et and et > st:
            durations.append(et - st)

    avg_ms = round(sum(durations) / len(durations)) if durations else 0

    return {
        "name": wf_name,
        "total": total,
        "failed": failed,
        "failure_rate_pct": failure_rate,
        "avg_ms": avg_ms,
    }


def _compute_trend(current_avg_ms: int, history_avgs: list) -> str:
    """Ratio-based trend label from a list of historical averages."""
    if not history_avgs:
        return "new"
    hist_avg = sum(history_avgs) / len(history_avgs)
    if hist_avg == 0:
        return "stable"
    ratio = current_avg_ms / hist_avg
    if ratio > 1.15:
        return "up"
    if ratio < 0.85:
        return "down"
    return "stable"


def _determine_trend(wf_name: str, current_avg_ms: int, cache: dict) -> str:
    """Compare current avg_ms against recent cached days to determine trend."""
    history_avgs = []
    for i in range(1, 8):
        past_date = _date_str(i)
        past = cache.get(past_date, {})
        for wf in past.get("workflows", []):
            if wf.get("name") == wf_name and wf.get("avg_ms", 0) > 0:
                history_avgs.append(wf["avg_ms"])

    if not history_avgs:
        return "new"
    return _compute_trend(current_avg_ms, history_avgs)


def generate_daily_digest(date_str: str = None, hours_back: int = 24) -> dict:
    """Generate a daily digest dict.  Stores result in _digest_cache."""
    global _digest_cache

    if date_str is None:
        date_str = _today_str()

    client = ConductorClient()
    defs = client.list_workflow_definitions()
    wf_names = sorted({d.get("name") for d in defs if d.get("name")})

    workflows = []
    regressions = []

    for wf_name in wf_names:
        stats = _compute_workflow_stats(client, wf_name, hours_back)
        trend = _determine_trend(wf_name, stats["avg_ms"], _digest_cache)
        stats["trend"] = trend
        workflows.append(stats)

        # Regression: >50% slower than 7-day avg
        history_avgs = []
        for i in range(1, 8):
            past_date = _date_str(i)
            past = _digest_cache.get(past_date, {})
            for wf in past.get("workflows", []):
                if wf.get("name") == wf_name and wf.get("avg_ms", 0) > 0:
                    history_avgs.append(wf["avg_ms"])

        if history_avgs and stats["avg_ms"] > 0:
            hist_avg = sum(history_avgs) / len(history_avgs)
            if hist_avg > 0 and stats["avg_ms"] > hist_avg * 1.5:
                regressions.append(
                    {
                        "workflow_name": wf_name,
                        "current_avg_ms": stats["avg_ms"],
                        "historical_avg_ms": round(hist_avg),
                        "pct_slower": round((stats["avg_ms"] / hist_avg - 1) * 100, 1),
                    }
                )

    # Worker health summary
    worker_queues = client.get_all_task_queues()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    worker_health = {}
    for task_type, info in worker_queues.items():
        workers = info.get("workerDetails", {})
        if not workers:
            worker_health[task_type] = "no_workers"
            continue
        last_poll = max(
            (w.get("lastPollTime", 0) for w in workers.values()), default=0
        )
        age_s = (now_ms - last_poll) / 1000 if last_poll else 999
        if age_s < 5:
            worker_health[task_type] = "healthy"
        elif age_s < 30:
            worker_health[task_type] = "slow_poll"
        else:
            worker_health[task_type] = "down"

    digest = {
        "date": date_str,
        "hours_back": hours_back,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflows": workflows,
        "regressions": regressions,
        "top_failures": sorted(workflows, key=lambda w: w["failed"], reverse=True)[:5],
        "worker_health": worker_health,
    }

    # Store in cache, evicting oldest if needed
    _digest_cache[date_str] = digest
    if len(_digest_cache) > _MAX_CACHE:
        oldest = sorted(_digest_cache.keys())[0]
        del _digest_cache[oldest]

    return digest


# ---------------------------------------------------------------------------
# APScheduler setup (runs generate_daily_digest at 06:00 UTC daily)
# ---------------------------------------------------------------------------

def init_scheduler(app):
    """Register the daily digest job with APScheduler.  Call from app factory."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()

        def _job():
            with app.app_context():
                try:
                    digest = generate_daily_digest()
                    app.logger.info("Scheduled daily digest generated.")
                    try:
                        from app.notification_provider import deliver_digest
                        result = deliver_digest(digest)
                        app.logger.info("digest_delivered: %s", result)
                    except Exception as exc:
                        app.logger.error("digest_delivery_error: %s", exc)
                except Exception as exc:
                    app.logger.error("Scheduled digest error: %s", exc)

        scheduler.add_job(_job, "cron", hour=6, minute=0, id="daily_digest")
        scheduler.start()
        app.logger.info("APScheduler started — daily digest job registered at 06:00 UTC")
        return scheduler
    except Exception as exc:
        app.logger.warning("Could not start APScheduler: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@digest_bp.get("/daily")
def daily_digest():
    """Return the daily digest for a given date.

    Query params:
      - date (YYYY-MM-DD, default today)
      - hours_back (default 24)
    """
    date_str = (request.args.get("date") or _today_str()).strip()
    hours_back = int(request.args.get("hours_back", 24))

    # Return cached value if available
    if date_str in _digest_cache:
        current_app.logger.info("daily_digest: serving cached result for %s", date_str)
        return jsonify(_digest_cache[date_str])

    # Compute on demand
    try:
        digest = generate_daily_digest(date_str=date_str, hours_back=hours_back)
        current_app.logger.info(
            "daily_digest: generated on-demand for %s workflows=%d",
            date_str,
            len(digest.get("workflows", [])),
        )
        return jsonify(digest)
    except Exception as exc:
        current_app.logger.error("daily_digest error: %s", exc, exc_info=True)
        return error_response(str(exc), "DIGEST_ERROR", 500)


@digest_bp.get("/workflow/<name>/history")
def workflow_history(name: str):
    """Return last 7 days of daily stats for a single workflow.

    Returns: { name, history: [{date, total, failed, avg_ms}] }
    """
    history = []
    for i in range(7):
        date_str = _date_str(i)
        cached = _digest_cache.get(date_str)
        if cached:
            for wf in cached.get("workflows", []):
                if wf.get("name") == name:
                    history.append(
                        {
                            "date": date_str,
                            "total": wf.get("total", 0),
                            "failed": wf.get("failed", 0),
                            "avg_ms": wf.get("avg_ms", 0),
                        }
                    )
                    break
        else:
            history.append({"date": date_str, "total": 0, "failed": 0, "avg_ms": 0})

    current_app.logger.info(
        "workflow_history: name=%s days=%d", name, len(history)
    )
    return jsonify({"name": name, "history": history})


@digest_bp.get("/recommendations")
def recommendations():
    """Return actionable recommendations based on current digest state.

    Checks:
      - Workflows with failure rate > 5%  -> elevated failure rate
      - Workers with slow_poll or down    -> worker health issue
      - Regressions (>50% slower)         -> performance regression
    """
    try:
        today = _today_str()
        if today not in _digest_cache:
            generate_daily_digest()

        digest = _digest_cache.get(today, {})
        recs = []

        for wf in digest.get("workflows", []):
            if wf.get("failure_rate_pct", 0) > 5:
                recs.append(
                    {
                        "severity": "error" if wf["failure_rate_pct"] > 20 else "warning",
                        "category": "failure_rate",
                        "message": (
                            f"{wf['name']} has an elevated failure rate of "
                            f"{wf['failure_rate_pct']}% ({wf['failed']}/{wf['total']} executions)"
                        ),
                        "workflow_name": wf["name"],
                    }
                )

        for task_type, health in digest.get("worker_health", {}).items():
            if health in ("slow_poll", "down", "no_workers"):
                recs.append(
                    {
                        "severity": "error" if health in ("down", "no_workers") else "warning",
                        "category": "worker_health",
                        "message": f"Worker health issue for task type '{task_type}': status={health}",
                        "workflow_name": None,
                    }
                )

        for reg in digest.get("regressions", []):
            recs.append(
                {
                    "severity": "warning",
                    "category": "regression",
                    "message": (
                        f"{reg['workflow_name']} is {reg['pct_slower']}% slower than the "
                        f"7-day average ({reg['current_avg_ms']}ms vs {reg['historical_avg_ms']}ms avg)"
                    ),
                    "workflow_name": reg["workflow_name"],
                }
            )

        # Sort: errors first, then warnings
        recs.sort(key=lambda r: (0 if r["severity"] == "error" else 1, r["category"]))

        current_app.logger.info("recommendations: count=%d", len(recs))
        return jsonify({"recommendations": recs, "generated_for": today})
    except Exception as exc:
        current_app.logger.error("recommendations error: %s", exc, exc_info=True)
        return error_response(str(exc), "RECOMMENDATIONS_ERROR", 500)
