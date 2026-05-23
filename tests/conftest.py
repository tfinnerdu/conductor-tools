"""pytest configuration, fixtures, and shared test helpers."""
import os
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the app uses an in-memory SQLite database for tests
# ---------------------------------------------------------------------------
os.environ.setdefault("CONDUCTOR_URL", "")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SERVICE_VERSION", "1.0.0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


@pytest.fixture()
def app():
    """Create a Flask test application."""
    from app import create_app
    test_app = create_app(config_override={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
    })
    with test_app.app_context():
        from app import db
        db.create_all()
        yield test_app
        db.drop_all()


@pytest.fixture()
def client(app):
    """Return a Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Mock ConductorClient fixtures
# ---------------------------------------------------------------------------

def _make_mock_conductor():
    """Build a MagicMock that mimics ConductorClient with realistic fixture data."""
    mock = MagicMock()
    # Real-path branch by default — route handlers that branch on client._mock
    # (only test_harness today) hit their live POST path under this fixture.
    mock._mock = False

    now_ms = int(time.time() * 1000)

    # search
    mock.search.return_value = {
        "totalHits": 3,
        "results": [
            {
                "workflowId": "wf-001",
                "workflowType": "order_fulfillment",
                "status": "COMPLETED",
                "startTime": now_ms - 7200000,
                "endTime": now_ms - 7000000,
                "correlationId": "order-1001",
                "input": {"orderId": 1001, "customerId": "cust-A"},
                "output": {"shipped": True},
                "version": 1,
            },
            {
                "workflowId": "wf-002",
                "workflowType": "order_fulfillment",
                "status": "FAILED",
                "startTime": now_ms - 3600000,
                "endTime": now_ms - 3500000,
                "correlationId": "order-1002",
                "input": {"orderId": 1002, "customerId": "cust-B"},
                "output": {},
                "version": 1,
            },
            {
                "workflowId": "wf-003",
                "workflowType": "student_enrollment",
                "status": "RUNNING",
                "startTime": now_ms - 600000,
                "endTime": None,
                "correlationId": "enroll-2001",
                "input": {"studentId": 2001},
                "output": {},
                "version": 2,
            },
        ],
    }

    # get_execution
    mock.get_execution.return_value = {
        "workflowId": "wf-001",
        "workflowType": "order_fulfillment",
        "status": "COMPLETED",
        "startTime": now_ms - 7200000,
        "endTime": now_ms - 7000000,
        "correlationId": "order-1001",
        "tasks": [
            {
                "taskId": "task-001",
                "taskType": "validate_order",
                "referenceTaskName": "validate_order_ref",
                "status": "COMPLETED",
                "startTime": now_ms - 7200000,
                "endTime": now_ms - 7180000,
                "outputData": {"valid": True, "amount": 49.99},
                "workerId": "worker-node-1",
            },
            {
                "taskId": "task-002",
                "taskType": "charge_payment",
                "referenceTaskName": "charge_payment_ref",
                "status": "COMPLETED",
                "startTime": now_ms - 7170000,
                "endTime": now_ms - 7100000,
                "outputData": {"charged": True},
                "workerId": "worker-node-2",
            },
        ],
    }

    # list_workflow_definitions
    mock.list_workflow_definitions.return_value = [
        {
            "name": "order_fulfillment",
            "version": 1,
            "description": "Order processing workflow",
            "tasks": [
                {"name": "validate_order", "taskReferenceName": "validate_order_ref", "type": "SIMPLE"},
                {"name": "charge_payment", "taskReferenceName": "charge_payment_ref", "type": "SIMPLE"},
            ],
        },
        {
            "name": "order_fulfillment",
            "version": 2,
            "description": "Order processing workflow v2",
            "tasks": [
                {"name": "validate_order", "taskReferenceName": "validate_order_ref", "type": "SIMPLE"},
                {"name": "charge_payment", "taskReferenceName": "charge_payment_ref", "type": "SIMPLE"},
                {"name": "ship_order", "taskReferenceName": "ship_order_ref", "type": "SIMPLE"},
            ],
        },
        {
            "name": "student_enrollment",
            "version": 1,
            "description": "Student enrollment",
            "tasks": [
                {"name": "enroll_student", "taskReferenceName": "enroll_ref", "type": "SIMPLE"},
            ],
        },
    ]

    # get_workflow_definition
    def _get_wf_def(name, version=None):
        v = version or 1
        tasks = {
            ("order_fulfillment", 1): [
                {"name": "validate_order", "taskReferenceName": "validate_order_ref", "type": "SIMPLE",
                 "inputParameters": {"orderId": "${workflow.input.orderId}"}},
                {"name": "charge_payment", "taskReferenceName": "charge_payment_ref", "type": "SIMPLE",
                 "inputParameters": {"amount": "${validate_order_ref.output.amount}"}},
            ],
            ("order_fulfillment", 2): [
                {"name": "validate_order", "taskReferenceName": "validate_order_ref", "type": "SIMPLE",
                 "inputParameters": {"orderId": "${workflow.input.orderId}"}},
                {"name": "charge_payment", "taskReferenceName": "charge_payment_ref", "type": "SIMPLE",
                 "inputParameters": {"amount": "${validate_order_ref.output.amount}"}},
                {"name": "ship_order", "taskReferenceName": "ship_order_ref", "type": "SIMPLE",
                 "inputParameters": {"orderId": "${workflow.input.orderId}"}},
            ],
        }.get((name, v), [])
        return {"name": name, "version": v, "tasks": tasks, "ownerEmail": "platform@doane.edu"}

    mock.get_workflow_definition.side_effect = _get_wf_def

    # get_all_task_queues
    mock.get_all_task_queues.return_value = {
        "validate_order": {
            "queueSize": 0,
            "workerDetails": {
                "worker-validate-1": {"lastPollTime": now_ms - 1000, "queueSize": 0},
                "worker-validate-2": {"lastPollTime": now_ms - 2000, "queueSize": 0},
            },
        },
        "charge_payment": {
            "queueSize": 3,
            "workerDetails": {
                "worker-charge-1": {"lastPollTime": now_ms - 35000, "queueSize": 3},
            },
        },
        "ghost_worker": {
            "queueSize": 5,
            "workerDetails": {},
        },
    }

    # get_task_performance
    mock.get_task_performance.return_value = {
        "taskType": "validate_order",
        "totalExecutions": 100,
        "completedCount": 95,
        "failedCount": 5,
        "successRate": 95.0,
        "avgDurationMs": 800,
        "minDurationMs": 120,
        "maxDurationMs": 4500,
        "p50DurationMs": 700,
        "p95DurationMs": 3200,
        "p99DurationMs": 4200,
    }

    # list_secrets
    mock.list_secrets.return_value = ["PAYMENT_API_KEY", "EMAIL_SECRET", "DB_PASSWORD"]

    # get_failures_by_task_type (Phase 2 — Reconciler)
    mock.get_failures_by_task_type.return_value = {
        "workflow_name": "student_enrollment",
        "hours_back": 24,
        "groups": [
            {
                "task_type": "ethos_get_person",
                "count": 8,
                "reasons": {"HTTP_404": 5, "TIMEOUT": 3},
                "workflow_ids": [f"mock-fail-{i:04d}" for i in range(8)],
            },
        ],
        "total_failures": 8,
    }

    # retry_workflow mock (returns None for all calls in mock mode)
    mock.retry_workflow.return_value = None

    return mock


@pytest.fixture()
def mock_conductor():
    """A configured MagicMock that replaces ConductorClient in route handlers."""
    return _make_mock_conductor()


@pytest.fixture()
def client_with_mock_conductor(app, mock_conductor):
    """Flask test client with ConductorClient patched in all routes."""
    from unittest.mock import MagicMock

    mock_sf = MagicMock()
    mock_sf.find_person_by_sis_id.return_value = {
        "records": [{"Id": "SF001", "FirstName": "Alex", "LastName": "Student",
                     "SIS_ID__c": "STU001", "Ethos_Guid__c": "mock-guid-001"}],
        "record_count": 1,
        "status": "ok",
        "diagnosis": "Record looks healthy",
    }
    mock_sf.find_person_by_guid.return_value = {
        "records": [{"Id": "SF001", "FirstName": "Alex", "LastName": "Student",
                     "SIS_ID__c": "STU001", "Ethos_Guid__c": "mock-guid-001"}],
        "record_count": 1,
        "status": "ok",
        "diagnosis": "Record looks healthy",
    }
    mock_sf.find_duplicate_accounts.return_value = []
    mock_sf.get_account.return_value = {"Id": "SF001", "FirstName": "Alex", "LastName": "Student"}
    mock_sf.check_health.return_value = {"ok": True, "detail": "not_configured", "latency_ms": None}

    mock_ethos = MagicMock()
    mock_ethos.get_person.return_value = {"id": "mock-guid", "content": {}}
    mock_ethos.get_recent_events.return_value = []
    mock_ethos.search_persons.return_value = []
    mock_ethos.check_health.return_value = {"ok": True, "detail": "not_configured", "latency_ms": None}
    mock_ethos._event_buffer = []

    with patch("app.routes.search.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.workers.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.batches.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.diff.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.secrets.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.jq_lab.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.reconciler.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.tracer.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.test_harness.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.digest.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.tracer.sf_provider", mock_sf), \
         patch("app.routes.tracer.ethos_provider", mock_ethos), \
         patch("app.routes.sf_console.sf_provider", mock_sf), \
         patch("app.routes.ethos.ethos_provider", mock_ethos):
        yield app.test_client()
