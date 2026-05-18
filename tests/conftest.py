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

    return mock


@pytest.fixture()
def mock_conductor():
    """A configured MagicMock that replaces ConductorClient in route handlers."""
    return _make_mock_conductor()


@pytest.fixture()
def client_with_mock_conductor(app, mock_conductor):
    """Flask test client with ConductorClient patched in all routes."""
    with patch("app.routes.search.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.workers.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.batches.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.diff.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.secrets.ConductorClient", return_value=mock_conductor), \
         patch("app.routes.jq_lab.ConductorClient", return_value=mock_conductor):
        yield app.test_client()
