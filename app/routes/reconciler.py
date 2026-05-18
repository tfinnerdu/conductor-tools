"""Reconciler routes — /api/v1/reconciler/*

Error Reconciler: groups failed workflow executions by the task type that
failed, surfaces error codes, and provides bulk-retry support.
"""
import re
import uuid

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient

reconciler_bp = Blueprint("reconciler", __name__, url_prefix="/api/v1/reconciler")


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


def _extract_error_code(reason: str) -> str:
    """Extract a short error code from a Conductor failure reason string.

    - 'DUPLICATE_VALUE: ...'  -> 'DUPLICATE_VALUE'
    - HTTP status patterns    -> 'HTTP_404', 'HTTP_429', etc.
    - Timeout patterns        -> 'TIMEOUT'
    - Falls back to first 60 chars of the reason string.
    """
    if not reason:
        return "UNKNOWN"

    reason_str = str(reason).strip()

    # Match timeout patterns first
    timeout_patterns = [
        r"(?i)timed?\s*out",
        r"(?i)timeout",
        r"(?i)deadline\s*exceeded",
    ]
    for pat in timeout_patterns:
        if re.search(pat, reason_str):
            return "TIMEOUT"

    # Match HTTP status code patterns like "HTTP 404", "status 429", "HTTP_404", "404 Not Found"
    http_match = re.search(r"(?i)(?:http[_ ]?|status[_ ]?)(\d{3})\b", reason_str)
    if http_match:
        return f"HTTP_{http_match.group(1)}"

    # Standalone HTTP code at the start
    leading_http = re.match(r"^(\d{3})\b", reason_str)
    if leading_http and 400 <= int(leading_http.group(1)) < 600:
        return f"HTTP_{leading_http.group(1)}"

    # Match UPPER_SNAKE_CASE error code at the start (e.g. DUPLICATE_VALUE: ...)
    code_match = re.match(r"^([A-Z][A-Z0-9_]{2,})\s*[:;]", reason_str)
    if code_match:
        return code_match.group(1)

    # Fall back to first 60 chars
    return reason_str[:60]


@reconciler_bp.get("/failures")
def list_failures():
    """Return failed workflow executions grouped by the last-failed task type.

    Query params:
      - workflow_name (optional)
      - hours_back (default 24)
      - page (default 1)
      - per_page (default 20)
    """
    workflow_name = request.args.get("workflow_name", "").strip()
    hours_back = int(request.args.get("hours_back", 24))
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 20))))

    try:
        client = ConductorClient()
        failures = client.get_failures_by_task_type(
            workflow_name=workflow_name, hours_back=hours_back
        )

        groups = failures.get("groups", [])
        total = len(groups)
        start = (page - 1) * per_page
        paginated = groups[start : start + per_page]

        current_app.logger.info(
            "reconciler failures: workflow=%s hours_back=%d groups=%d",
            workflow_name or "*",
            hours_back,
            total,
        )
        return jsonify(
            {
                "groups": paginated,
                "total": total,
                "page": page,
                "per_page": per_page,
                "workflow_name": workflow_name or None,
                "hours_back": hours_back,
            }
        )
    except Exception as exc:
        current_app.logger.error("list_failures error: %s", exc, exc_info=True)
        return _error(str(exc), "RECONCILER_ERROR", 500)


@reconciler_bp.get("/failures/<workflow_id>")
def get_failure_detail(workflow_id: str):
    """Return full failure detail for one workflow execution."""
    try:
        client = ConductorClient()
        execution = client.get_execution(workflow_id, include_tasks=True)

        tasks = execution.get("tasks", [])
        failed_task = None
        for task in tasks:
            if task.get("status") == "FAILED":
                failed_task = task
                break

        # Find the last task that ran if none is FAILED (terminated mid-run)
        if failed_task is None and tasks:
            failed_task = tasks[-1]

        detail = {
            "workflowId": workflow_id,
            "workflowType": execution.get("workflowType"),
            "status": execution.get("status"),
            "startTime": execution.get("startTime"),
            "endTime": execution.get("endTime"),
            "workflowInput": execution.get("input", {}),
            "failedTask": None,
        }

        if failed_task:
            reason = failed_task.get("reasonForIncompletion") or failed_task.get(
                "outputData", {}
            ).get("error", "")
            detail["failedTask"] = {
                "taskId": failed_task.get("taskId"),
                "taskType": failed_task.get("taskType"),
                "referenceTaskName": failed_task.get("referenceTaskName"),
                "status": failed_task.get("status"),
                "startTime": failed_task.get("startTime"),
                "endTime": failed_task.get("endTime"),
                "retryCount": failed_task.get("retryCount", 0),
                "reasonForIncompletion": reason,
                "errorCode": _extract_error_code(reason),
                "outputData": failed_task.get("outputData", {}),
            }

        # Extract SIS_ID from workflow input
        wf_input = execution.get("input", {})
        sis_id = wf_input.get("sis_id") or wf_input.get("sisId") or wf_input.get("SIS_ID")
        detail["sisId"] = sis_id

        return jsonify(detail)
    except Exception as exc:
        current_app.logger.error("get_failure_detail error: %s", exc, exc_info=True)
        return _error(str(exc), "DETAIL_ERROR", 500)


@reconciler_bp.post("/failures/bulk-retry")
def bulk_retry():
    """Retry multiple failed workflow executions.

    Body: {"workflow_ids": ["id1", "id2", ...]}
    Returns: {"retried": N, "errors": [...]}
    """
    body = request.get_json(force=True) or {}
    workflow_ids = body.get("workflow_ids", [])

    if not isinstance(workflow_ids, list):
        return _error("workflow_ids must be an array", "VALIDATION_ERROR")
    if len(workflow_ids) == 0:
        return _error("workflow_ids must not be empty", "VALIDATION_ERROR")
    if len(workflow_ids) > 500:
        return _error("Cannot retry more than 500 workflows at once", "LIMIT_EXCEEDED")

    client = ConductorClient()
    retried = 0
    errors = []

    for wf_id in workflow_ids:
        try:
            client.retry_workflow(str(wf_id))
            retried += 1
        except Exception as exc:
            errors.append({"workflowId": wf_id, "error": str(exc)})

    current_app.logger.info(
        "bulk_retry: attempted=%d retried=%d errors=%d",
        len(workflow_ids),
        retried,
        len(errors),
    )
    return jsonify({"retried": retried, "errors": errors})


@reconciler_bp.get("/summary")
def failure_summary():
    """Return a categorized failure summary across all watched workflow types.

    Groups by: workflow_name -> task_type -> error_code
    Query params:
      - hours_back (default 24)
    """
    hours_back = int(request.args.get("hours_back", 24))

    try:
        client = ConductorClient()
        defs = client.list_workflow_definitions()

        # Collect unique workflow names
        wf_names = list({d.get("name") for d in defs if d.get("name")})

        summary = {}
        for wf_name in sorted(wf_names):
            failures = client.get_failures_by_task_type(
                workflow_name=wf_name, hours_back=hours_back
            )
            groups = failures.get("groups", [])
            if groups:
                wf_entry = {}
                for group in groups:
                    task_type = group.get("task_type", "unknown")
                    reasons = group.get("reasons", {})
                    wf_entry[task_type] = {
                        "count": group.get("count", 0),
                        "error_codes": reasons,
                    }
                summary[wf_name] = wf_entry

        total_failed = sum(
            grp.get("count", 0)
            for wf_data in summary.values()
            for grp in wf_data.values()
        )

        current_app.logger.info(
            "failure_summary: hours_back=%d workflows_with_failures=%d total_failed=%d",
            hours_back,
            len(summary),
            total_failed,
        )
        return jsonify(
            {
                "summary": summary,
                "hours_back": hours_back,
                "total_failed": total_failed,
                "workflows_analyzed": len(wf_names),
            }
        )
    except Exception as exc:
        current_app.logger.error("failure_summary error: %s", exc, exc_info=True)
        return _error(str(exc), "SUMMARY_ERROR", 500)
