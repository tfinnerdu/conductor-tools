"""ConductorClient — HTTP wrapper around the Orkes Conductor REST API.

Requires a live Conductor instance: ``CONDUCTOR_URL`` must point at a real
Conductor. There is no mock fallback — when an upstream call fails the error
propagates to the caller so it surfaces in the UI, rather than being masked by
fabricated fixture data.
"""
import os

import requests


class ConductorClient:
    """Thin HTTP client for the Orkes/Netflix Conductor REST API."""

    def __init__(self):
        self.base_url = os.environ.get("CONDUCTOR_URL", "").rstrip("/")
        self.api_key = os.environ.get("CONDUCTOR_API_KEY")

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def get_headers(self) -> dict:
        """Return HTTP headers, including auth if an API key is configured."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-Authorization"] = self.api_key
        return headers

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str = "",
        free_text: str = "",
        status: str = "",
        workflow_type: str = "",
        start: int = 0,
        size: int = 100,
    ) -> dict:
        """Search workflow executions.

        Returns a dict matching the Conductor SearchResultWorkflowSummary shape:
        {"totalHits": N, "results": [...]}
        """
        query_str = self._build_query(query, status, workflow_type)
        params = {
            "start": start,
            "size": size,
            "sort": "startTime:DESC",
        }
        if query_str:
            params["query"] = query_str
        if free_text:
            params["freeText"] = free_text

        resp = requests.get(
            f"{self.base_url}/api/workflow/search",
            headers=self.get_headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def get_execution(self, workflow_id: str, include_tasks: bool = True) -> dict:
        """Fetch a single workflow execution by ID."""
        resp = requests.get(
            f"{self.base_url}/api/workflow/{workflow_id}",
            headers=self.get_headers(),
            params={"includeTasks": str(include_tasks).lower()},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Workflow control
    # ------------------------------------------------------------------

    def retry_workflow(self, workflow_id: str) -> None:
        """Retry a failed workflow execution."""
        requests.post(
            f"{self.base_url}/api/workflow/{workflow_id}/retry",
            headers=self.get_headers(),
            timeout=10,
        ).raise_for_status()

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def get_workflow_definition(self, name: str, version=None) -> dict:
        """Fetch a workflow definition."""
        params = {}
        if version is not None:
            params["version"] = version
        resp = requests.get(
            f"{self.base_url}/api/metadata/workflow/{name}",
            headers=self.get_headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def list_workflow_definitions(self) -> list:
        """List all workflow definitions (metadata summaries)."""
        resp = requests.get(
            f"{self.base_url}/api/metadata/workflow",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_definition(self, task_type: str) -> dict:
        """Fetch a task definition by task type name."""
        resp = requests.get(
            f"{self.base_url}/api/metadata/taskdefs/{task_type}",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Worker / Task queue
    # ------------------------------------------------------------------

    def get_task_queue_info(self, task_type: str) -> dict:
        """Return queue depth and poll data for a single task type."""
        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/all/verbose",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get(task_type, {})

    def get_all_task_queues(self) -> dict:
        """Return verbose queue info for all task types."""
        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/all/verbose",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_worker_last_poll(self, task_type: str) -> list:
        """Return poll data (list of worker poll records) for a task type."""
        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/polldata",
            headers=self.get_headers(),
            params={"taskType": task_type},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_performance(self, task_type: str) -> dict:
        """Return task execution stats for a given task type."""
        result = self.search(
            query=f"taskType='{task_type}'",
            status="COMPLETED",
            size=200,
        )
        return _compute_performance(task_type, result.get("results", []))

    # ------------------------------------------------------------------
    # Reconciler
    # ------------------------------------------------------------------

    def get_failures_by_task_type(self, workflow_name: str, hours_back: int = 24) -> dict:
        """Return failed executions grouped by the last-failed task type."""
        query_parts = ["status='FAILED'"]
        if workflow_name:
            query_parts.append(f"workflowType='{workflow_name}'")
        result = self.search(
            query=" AND ".join(query_parts),
            status="FAILED",
            workflow_type=workflow_name,
            size=500,
        )
        return _group_failures_by_task_type(result.get("results", []), workflow_name)

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def list_secrets(self) -> list:
        """List secret names from Conductor."""
        resp = requests.get(
            f"{self.base_url}/api/secrets",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def set_secret(self, name: str, value: str) -> None:
        """Create or update a secret."""
        requests.put(
            f"{self.base_url}/api/secrets/{name}",
            headers=self.get_headers(),
            json=value,
            timeout=10,
        ).raise_for_status()

    def delete_secret(self, name: str) -> None:
        """Delete a secret by name."""
        requests.delete(
            f"{self.base_url}/api/secrets/{name}",
            headers=self.get_headers(),
            timeout=10,
        ).raise_for_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_query(self, custom: str, status: str, workflow_type: str) -> str:
        """Compose a Conductor query string from filter parts."""
        parts = []
        if custom:
            parts.append(custom.strip())
        if status:
            parts.append(f"status='{status}'")
        if workflow_type:
            parts.append(f"workflowType='{workflow_type}'")
        return " AND ".join(parts)


# ---------------------------------------------------------------------------
# Aggregation helpers (operate on real Conductor search results)
# ---------------------------------------------------------------------------

def _group_failures_by_task_type(executions: list, workflow_name: str) -> dict:
    """Group a list of FAILED executions by last-failed task type."""
    from collections import defaultdict

    groups_map: dict = defaultdict(lambda: {"count": 0, "reasons": {}, "workflow_ids": []})

    for ex in executions:
        tasks = ex.get("tasks", [])
        failed_task = None
        for t in tasks:
            if t.get("status") == "FAILED":
                failed_task = t
                break
        if failed_task is None and tasks:
            failed_task = tasks[-1]

        task_type = (failed_task or {}).get("taskType", "unknown")
        reason = (failed_task or {}).get("reasonForIncompletion") or ""
        wf_id = ex.get("workflowId", "unknown")

        entry = groups_map[task_type]
        entry["count"] += 1
        entry["workflow_ids"].append(wf_id)
        if reason:
            entry["reasons"][reason] = entry["reasons"].get(reason, 0) + 1

    groups = [
        {
            "task_type": tt,
            "count": data["count"],
            "reasons": data["reasons"],
            "workflow_ids": data["workflow_ids"],
        }
        for tt, data in sorted(groups_map.items(), key=lambda x: x[1]["count"], reverse=True)
    ]

    return {
        "workflow_name": workflow_name or None,
        "hours_back": 24,
        "groups": groups,
        "total_failures": sum(g["count"] for g in groups),
    }


def _compute_performance(task_type: str, executions: list) -> dict:
    """Compute performance stats from a list of execution records."""
    durations = []
    failed = 0
    for ex in executions:
        st = ex.get("startTime", 0)
        et = ex.get("endTime", 0)
        status = ex.get("status", "")
        if status == "FAILED":
            failed += 1
        if st and et and et > st:
            durations.append(et - st)

    total = len(executions)
    completed = total - failed
    if durations:
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        avg = sum(durations_sorted) / n
        p50 = durations_sorted[int(n * 0.50)]
        p95 = durations_sorted[int(n * 0.95)]
        p99 = durations_sorted[min(int(n * 0.99), n - 1)]
        min_d = durations_sorted[0]
        max_d = durations_sorted[-1]
    else:
        avg = p50 = p95 = p99 = min_d = max_d = 0

    return {
        "taskType": task_type,
        "totalExecutions": total,
        "completedCount": completed,
        "failedCount": failed,
        "successRate": round((completed / total * 100) if total else 0, 2),
        "avgDurationMs": round(avg),
        "minDurationMs": round(min_d),
        "maxDurationMs": round(max_d),
        "p50DurationMs": round(p50),
        "p95DurationMs": round(p95),
        "p99DurationMs": round(p99),
    }
