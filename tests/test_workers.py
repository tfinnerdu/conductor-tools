"""Tests for Workers routes."""
import json
import time


class TestClassifyWorker:
    """Unit tests for the _classify_worker helper function."""

    def _get_fn(self):
        from app.routes.workers import _classify_worker
        return _classify_worker

    def test_classify_healthy(self):
        fn = self._get_fn()
        # Less than 5 seconds since poll
        assert fn(2.5) == "healthy"
        assert fn(0) == "healthy"
        assert fn(4.9) == "healthy"

    def test_classify_slow_poll(self):
        fn = self._get_fn()
        # Between 5 and 30 seconds
        assert fn(5) == "slow_poll"
        assert fn(15) == "slow_poll"
        assert fn(29.9) == "slow_poll"

    def test_classify_down(self):
        fn = self._get_fn()
        # 30+ seconds
        assert fn(30) == "down"
        assert fn(60) == "down"
        assert fn(9999) == "down"

    def test_classify_boundary_5(self):
        fn = self._get_fn()
        # Exactly at the 5s boundary
        assert fn(4.999) == "healthy"
        assert fn(5.0) == "slow_poll"

    def test_classify_boundary_30(self):
        fn = self._get_fn()
        # Exactly at the 30s boundary
        assert fn(29.999) == "slow_poll"
        assert fn(30.0) == "down"


class TestClassifyNoWorkers:
    """Test the _classify_task_type helper for no-worker scenarios."""

    def test_classify_no_workers(self):
        from app.routes.workers import _classify_task_type
        result = _classify_task_type([], queue_size=5)
        assert result["status"] == "no_workers"
        assert result["workerCount"] == 0
        assert result["queueDepth"] == 5


class TestWorkerStatusEndpoint:
    """Integration tests for GET /api/v1/workers/status."""

    def test_worker_status_endpoint(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/workers/status")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "workers" in data
        assert "totalTaskTypes" in data
        assert "summaryCounts" in data
        assert "refreshedAt" in data

        summary = data["summaryCounts"]
        assert "healthy" in summary
        assert "slow_poll" in summary
        assert "down" in summary
        assert "no_workers" in summary

        workers = data["workers"]
        assert len(workers) == 3  # validate_order, charge_payment, ghost_worker

        # Find validate_order — it was polled 1-2s ago, should be healthy
        vo = next((w for w in workers if w["taskType"] == "validate_order"), None)
        assert vo is not None
        assert vo["status"] == "healthy"
        assert vo["workerCount"] == 2

        # Find charge_payment — polled 35s ago, should be down
        cp = next((w for w in workers if w["taskType"] == "charge_payment"), None)
        assert cp is not None
        assert cp["status"] == "down"

        # Find ghost_worker — no worker details, should be no_workers
        gw = next((w for w in workers if w["taskType"] == "ghost_worker"), None)
        assert gw is not None
        assert gw["status"] == "no_workers"

    def test_worker_performance_endpoint(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/workers/validate_order/performance")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["taskType"] == "validate_order"
        assert "successRate" in data
        assert "avgDurationMs" in data
        assert "p95DurationMs" in data
        assert data["totalExecutions"] == 100
        assert data["successRate"] == 95.0
