"""ConductorClient — HTTP wrapper around the Orkes Conductor REST API.

By default this client makes real calls and lets errors propagate — there is
no silent fallback to fixture data. Setting SHOW_MOCK=1 in the environment
flips every method to return realistic mock fixtures instead, for offline
testing. SHOW_MOCK is an EXPLICIT, opt-in flag — never an error-recovery path.
"""
import os
import time

import requests

from app.utils.env import show_mock


class ConductorClient:
    """Thin HTTP client for the Orkes/Netflix Conductor REST API."""

    def __init__(self):
        self.base_url = os.environ.get("CONDUCTOR_URL", "").rstrip("/")
        self.api_key = os.environ.get("CONDUCTOR_API_KEY")
        self._mock = show_mock()

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
        """Search workflow executions."""
        if self._mock:
            return _mock_search(query, status, workflow_type, start, size)

        query_str = self._build_query(query, status, workflow_type)
        params = {"start": start, "size": size, "sort": "startTime:DESC"}
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
        if self._mock:
            return _mock_execution(workflow_id)

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
        if self._mock:
            return

        requests.post(
            f"{self.base_url}/api/workflow/{workflow_id}/retry",
            headers=self.get_headers(),
            timeout=10,
        ).raise_for_status()

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def get_workflow_definition(self, name: str, version=None) -> dict:
        if self._mock:
            return _mock_workflow_definition(name, version)

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
        if self._mock:
            return _mock_workflow_definitions()

        resp = requests.get(
            f"{self.base_url}/api/metadata/workflow",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_definition(self, task_type: str) -> dict:
        if self._mock:
            return _mock_task_definition(task_type)

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
        if self._mock:
            return _mock_task_queue_info(task_type)

        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/all/verbose",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get(task_type, {})

    def get_all_task_queues(self) -> dict:
        if self._mock:
            return _mock_all_task_queues()

        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/all/verbose",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_worker_last_poll(self, task_type: str) -> list:
        if self._mock:
            return _mock_worker_poll_data(task_type)

        resp = requests.get(
            f"{self.base_url}/api/tasks/queue/polldata",
            headers=self.get_headers(),
            params={"taskType": task_type},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_performance(self, task_type: str) -> dict:
        if self._mock:
            return _mock_task_performance(task_type)

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
        if self._mock:
            return _mock_failures_by_task_type(workflow_name, hours_back)

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
        if self._mock:
            return _mock_secret_names()

        resp = requests.get(
            f"{self.base_url}/api/secrets",
            headers=self.get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def set_secret(self, name: str, value: str) -> None:
        if self._mock:
            return

        requests.put(
            f"{self.base_url}/api/secrets/{name}",
            headers=self.get_headers(),
            json=value,
            timeout=10,
        ).raise_for_status()

    def delete_secret(self, name: str) -> None:
        if self._mock:
            return

        requests.delete(
            f"{self.base_url}/api/secrets/{name}",
            headers=self.get_headers(),
            timeout=10,
        ).raise_for_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_query(self, custom: str, status: str, workflow_type: str) -> str:
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


# ---------------------------------------------------------------------------
# Mock fixture data — used only when SHOW_MOCK is enabled
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _ago_ms(seconds: int) -> int:
    return _now_ms() - seconds * 1000


def _mock_search(query, status, workflow_type, start, size) -> dict:
    results = [
        {
            "workflowId": f"mock-wf-{i:04d}",
            "workflowType": workflow_type or "order_fulfillment",
            "status": status or ("COMPLETED" if i % 3 != 0 else "FAILED"),
            "startTime": _ago_ms(3600 * (i + 1)),
            "endTime": _ago_ms(3600 * (i + 1) - 300),
            "correlationId": f"order-{1000 + i}",
            "input": {"orderId": 1000 + i, "customerId": f"cust-{i}"},
            "output": {"shipped": True} if i % 3 != 0 else {},
            "version": 1,
        }
        for i in range(min(size, 25))
    ]
    return {"totalHits": 25, "results": results[start : start + size]}


def _mock_execution(workflow_id: str) -> dict:
    return {
        "workflowId": workflow_id,
        "workflowType": "order_fulfillment",
        "status": "COMPLETED",
        "startTime": _ago_ms(3600),
        "endTime": _ago_ms(3300),
        "correlationId": "order-1001",
        "input": {"orderId": 1001, "customerId": "cust-1"},
        "output": {"shipped": True, "trackingNumber": "TRK-999"},
        "tasks": [
            {
                "taskId": f"{workflow_id}-task-1",
                "taskType": "validate_order",
                "status": "COMPLETED",
                "startTime": _ago_ms(3600),
                "endTime": _ago_ms(3580),
                "outputData": {"valid": True},
                "workerId": "worker-node-1",
            },
            {
                "taskId": f"{workflow_id}-task-2",
                "taskType": "charge_payment",
                "status": "COMPLETED",
                "startTime": _ago_ms(3570),
                "endTime": _ago_ms(3540),
                "outputData": {"charged": True, "amount": 99.99},
                "workerId": "worker-node-2",
            },
            {
                "taskId": f"{workflow_id}-task-3",
                "taskType": "ship_order",
                "status": "COMPLETED",
                "startTime": _ago_ms(3530),
                "endTime": _ago_ms(3300),
                "outputData": {"shipped": True, "trackingNumber": "TRK-999"},
                "workerId": "worker-node-1",
            },
        ],
        "version": 1,
    }


def _mock_workflow_definition(name: str, version=None) -> dict:
    v = version or 1
    return {
        "name": name or "order_fulfillment",
        "version": v,
        "description": f"Mock definition for {name} v{v}",
        "tasks": [
            {
                "name": "validate_order",
                "taskReferenceName": "validate_order_ref",
                "type": "SIMPLE",
                "inputParameters": {"orderId": "${workflow.input.orderId}"},
            },
            {
                "name": "charge_payment",
                "taskReferenceName": "charge_payment_ref",
                "type": "SIMPLE",
                "inputParameters": {"amount": "${validate_order_ref.output.amount}"},
            },
            {
                "name": "ship_order",
                "taskReferenceName": "ship_order_ref",
                "type": "SIMPLE",
                "inputParameters": {"orderId": "${workflow.input.orderId}"},
            },
        ],
        "inputParameters": ["orderId", "customerId"],
        "outputParameters": {
            "shipped": "${ship_order_ref.output.shipped}",
            "trackingNumber": "${ship_order_ref.output.trackingNumber}",
        },
        "schemaVersion": 2,
        "restartable": True,
        "ownerEmail": "platform@doane.edu",
    }


def _mock_workflow_definitions() -> list:
    wf_names = [
        "order_fulfillment",
        "student_enrollment",
        "financial_aid_processing",
        "course_registration",
        "transcript_generation",
        "employee_onboarding",
        "payroll_processing",
    ]
    defs = []
    for name in wf_names:
        for v in (1, 2):
            defs.append(
                {
                    "name": name,
                    "version": v,
                    "description": f"Workflow: {name.replace('_', ' ').title()}",
                    "ownerEmail": "platform@doane.edu",
                    "schemaVersion": 2,
                    "tasks": [],
                }
            )
    return defs


def _mock_task_definition(task_type: str) -> dict:
    return {
        "name": task_type,
        "description": f"Mock task definition for {task_type}",
        "retryCount": 3,
        "timeoutSeconds": 300,
        "inputKeys": ["input1", "input2"],
        "outputKeys": ["output1"],
        "timeoutPolicy": "TIME_OUT_WF",
        "retryLogic": "FIXED",
        "retryDelaySeconds": 60,
        "responseTimeoutSeconds": 600,
        "concurrentExecLimit": 10,
        "rateLimitFrequencyInSeconds": 1,
        "rateLimitPerFrequency": 50,
        "ownerEmail": "platform@doane.edu",
    }


def _mock_task_queue_info(task_type: str) -> dict:
    import random
    return {"queueSize": random.randint(0, 15)}


def _mock_all_task_queues() -> dict:
    task_types = [
        "validate_order",
        "charge_payment",
        "ship_order",
        "send_notification",
        "enroll_student",
        "process_financial_aid",
        "generate_transcript",
    ]
    now_ms = _now_ms()
    result = {}
    for i, tt in enumerate(task_types):
        last_poll_offset = (i % 3) * 10000
        result[tt] = {
            "queueSize": i * 2,
            "workerDetails": {
                f"worker-{tt}-node-{j}": {
                    "lastPollTime": now_ms - last_poll_offset,
                    "queueSize": i,
                }
                for j in range(1, 3)
            },
        }
    return result


def _mock_worker_poll_data(task_type: str) -> list:
    now_ms = _now_ms()
    return [
        {
            "queueName": task_type,
            "workerId": f"worker-{task_type}-node-{i}",
            "lastPollTime": now_ms - (i * 2000),
            "domain": None,
        }
        for i in range(1, 3)
    ]


def _mock_task_performance(task_type: str) -> dict:
    return {
        "taskType": task_type,
        "totalExecutions": 342,
        "completedCount": 325,
        "failedCount": 17,
        "successRate": 95.03,
        "avgDurationMs": 1450,
        "minDurationMs": 210,
        "maxDurationMs": 12340,
        "p50DurationMs": 1200,
        "p95DurationMs": 4500,
        "p99DurationMs": 9800,
    }


def _mock_secret_names() -> list:
    return [
        "PAYMENT_API_KEY",
        "EMAIL_SERVICE_SECRET",
        "DATABASE_PASSWORD",
        "SFTP_PRIVATE_KEY",
        "OAUTH_CLIENT_SECRET",
    ]


def _mock_failures_by_task_type(workflow_name: str, hours_back: int) -> dict:
    groups = [
        {
            "task_type": "ethos_get_person",
            "count": 12,
            "reasons": {"HTTP_404": 7, "HTTP_429": 3, "TIMEOUT": 2},
            "workflow_ids": [f"mock-fail-ethos-{i:04d}" for i in range(12)],
        },
        {
            "task_type": "colleague_upsert_person",
            "count": 5,
            "reasons": {
                "DUPLICATE_VALUE: Person already exists with SIS_ID": 4,
                "VALIDATION_ERROR: Missing required field dateOfBirth": 1,
            },
            "workflow_ids": [f"mock-fail-colleague-{i:04d}" for i in range(5)],
        },
        {
            "task_type": "salesforce_sync",
            "count": 3,
            "reasons": {"HTTP_500": 2, "TIMEOUT": 1},
            "workflow_ids": [f"mock-fail-sf-{i:04d}" for i in range(3)],
        },
    ]
    if workflow_name and workflow_name not in (
        "student_enrollment", "financial_aid_processing", "employee_onboarding"
    ):
        groups = []

    return {
        "workflow_name": workflow_name or None,
        "hours_back": hours_back,
        "groups": groups,
        "total_failures": sum(g["count"] for g in groups),
    }
