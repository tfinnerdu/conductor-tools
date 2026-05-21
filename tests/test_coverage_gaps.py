"""Coverage gap tests — drives every uncovered line to 100%.

Organized by module. Each section targets the specific missing lines
identified by pytest-cov. Every test here exists because a real branch
was unreachable from existing tests, not to pad numbers.
"""
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# app/__init__.py  lines 80-81  (db.create_all() exception handler)
# =============================================================================

class TestAppInit:
    def test_db_create_all_exception_is_swallowed(self):
        """create_app must not raise when db.create_all() fails."""
        from app import create_app
        with patch("app.db.create_all", side_effect=Exception("db unavailable")):
            app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        assert app is not None


# =============================================================================
# app/routes/__init__.py  line 10  (index view)
# =============================================================================

class TestMainRoute:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


# =============================================================================
# app/health_checks.py
# line 37   — X-Authorization set when api_key present
# lines 53-55 — Timeout + generic exception in check_conductor_live
# lines 96-98 — generic exception in check_conductor_functional
# =============================================================================

class TestHealthChecksGaps:
    def test_x_authorization_set_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor")
        monkeypatch.setenv("CONDUCTOR_API_KEY", "my-key")
        from app.health_checks import check_conductor_live
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("app.health_checks.requests.get", return_value=mock_resp) as mock_get:
            check_conductor_live()
            assert mock_get.call_args[1]["headers"]["X-Authorization"] == "my-key"

    def test_check_conductor_live_generic_exception(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor")
        monkeypatch.delenv("CONDUCTOR_API_KEY", raising=False)
        from app.health_checks import check_conductor_live
        with patch("app.health_checks.requests.get", side_effect=ConnectionError("refused")):
            result = check_conductor_live()
        assert result["ok"] is False
        assert "refused" in result["detail"]

    def test_check_conductor_functional_exception(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor")
        from app.health_checks import check_conductor_functional
        with patch("app.health_checks.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("boom")
            result = check_conductor_functional()
        assert result["ok"] is False
        assert "boom" in result["detail"]


# =============================================================================
# app/conductor_client.py — all live paths + all mock fixture functions
# =============================================================================

class TestConductorClientMockPaths:
    """Drive mock-mode paths (lines 54, 86, etc.) by calling client directly."""

    def _mock_client(self):
        os.environ.pop("CONDUCTOR_URL", None)
        from app.conductor_client import ConductorClient
        return ConductorClient()

    def test_search_mock_mode(self):
        c = self._mock_client()
        result = c.search(workflow_type="EDA_Person_Sync", status="FAILED")
        assert "results" in result
        assert "totalHits" in result

    def test_search_mock_with_free_text(self):
        c = self._mock_client()
        result = c.search(free_text="STU12345", size=5)
        assert len(result["results"]) <= 5

    def test_get_execution_mock_mode(self):
        c = self._mock_client()
        result = c.get_execution("mock-id-001")
        assert result["workflowId"] == "mock-id-001"
        assert "tasks" in result

    def test_retry_workflow_mock_mode_returns_none(self):
        c = self._mock_client()
        assert c.retry_workflow("mock-wf") is None

    def test_get_workflow_definition_mock_mode(self):
        c = self._mock_client()
        result = c.get_workflow_definition("EDA_Person_Sync", version=2)
        assert result["name"] == "EDA_Person_Sync"
        assert result["version"] == 2

    def test_get_workflow_definition_no_version(self):
        c = self._mock_client()
        result = c.get_workflow_definition("some_workflow")
        assert "tasks" in result

    def test_list_workflow_definitions_mock_mode(self):
        c = self._mock_client()
        result = c.list_workflow_definitions()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_task_definition_mock_mode(self):
        c = self._mock_client()
        result = c.get_task_definition("ethos_get_by_id")
        assert result["name"] == "ethos_get_by_id"

    def test_get_task_queue_info_mock_mode(self):
        c = self._mock_client()
        result = c.get_task_queue_info("validate_order")
        assert "queueSize" in result

    def test_get_all_task_queues_mock_mode(self):
        c = self._mock_client()
        result = c.get_all_task_queues()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_worker_last_poll_mock_mode(self):
        c = self._mock_client()
        result = c.get_worker_last_poll("validate_order")
        assert isinstance(result, list)
        assert len(result) > 0
        assert "workerId" in result[0]

    def test_get_task_performance_mock_mode(self):
        c = self._mock_client()
        result = c.get_task_performance("validate_order")
        assert "avgDurationMs" in result
        assert "successRate" in result

    def test_list_secrets_mock_mode(self):
        c = self._mock_client()
        result = c.list_secrets()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_set_secret_mock_mode_returns_none(self):
        c = self._mock_client()
        assert c.set_secret("MY_KEY", "value") is None

    def test_delete_secret_mock_mode_returns_none(self):
        c = self._mock_client()
        assert c.delete_secret("MY_KEY") is None

    def test_get_failures_by_task_type_mock_mode(self):
        c = self._mock_client()
        result = c.get_failures_by_task_type("EDA_Person_Sync", hours_back=24)
        assert "groups" in result
        assert "total_failures" in result

    def test_build_query_all_parts(self):
        c = self._mock_client()
        q = c._build_query("correlationId=abc", "FAILED", "EDA_Person_Sync")
        assert "FAILED" in q
        assert "EDA_Person_Sync" in q
        assert "correlationId=abc" in q

    def test_build_query_empty(self):
        c = self._mock_client()
        assert c._build_query("", "", "") == ""


class TestConductorClientLivePaths:
    """Drive live paths by setting CONDUCTOR_URL and mocking requests."""

    def _live_client(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor.test")
        monkeypatch.delenv("CONDUCTOR_API_KEY", raising=False)
        from app.conductor_client import ConductorClient
        return ConductorClient()

    def _ok_resp(self, body):
        r = MagicMock()
        r.json.return_value = body
        r.raise_for_status.return_value = None
        return r

    def test_search_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"totalHits": 1, "results": []})):
            result = c.search(workflow_type="EDA", status="FAILED")
        assert result["totalHits"] == 1

    def test_search_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=ConnectionError()):
            result = c.search()
        assert "results" in result  # mock fallback

    def test_search_includes_free_text_param(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"totalHits": 0, "results": []})) as mock_get:
            c.search(free_text="STU12345")
            params = mock_get.call_args[1]["params"]
        assert params["freeText"] == "STU12345"

    def test_get_execution_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"workflowId": "abc", "tasks": []})):
            result = c.get_execution("abc")
        assert result["workflowId"] == "abc"

    def test_get_execution_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_execution("abc")
        assert "workflowId" in result

    def test_get_execution_include_tasks_false(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"workflowId": "x"})) as mock_get:
            c.get_execution("x", include_tasks=False)
            assert mock_get.call_args[1]["params"]["includeTasks"] == "false"

    def test_retry_workflow_live(self, monkeypatch):
        c = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("app.conductor_client.requests.post", return_value=mock_resp):
            c.retry_workflow("wf-123")  # must not raise

    def test_get_workflow_definition_live_with_version(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"name": "EDA", "version": 3})) as mock_get:
            result = c.get_workflow_definition("EDA", version=3)
            assert mock_get.call_args[1]["params"]["version"] == 3
        assert result["version"] == 3

    def test_get_workflow_definition_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_workflow_definition("EDA")
        assert "tasks" in result

    def test_list_workflow_definitions_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp([{"name": "wf1"}])):
            result = c.list_workflow_definitions()
        assert result[0]["name"] == "wf1"

    def test_list_workflow_definitions_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.list_workflow_definitions()
        assert isinstance(result, list)

    def test_get_task_definition_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"name": "my_task"})):
            result = c.get_task_definition("my_task")
        assert result["name"] == "my_task"

    def test_get_task_definition_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_task_definition("my_task")
        assert "name" in result

    def test_get_task_queue_info_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"my_task": {"queueSize": 5}})):
            result = c.get_task_queue_info("my_task")
        assert result["queueSize"] == 5

    def test_get_task_queue_info_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_task_queue_info("my_task")
        assert "queueSize" in result

    def test_get_all_task_queues_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        payload = {"task_a": {"queueSize": 2}}
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp(payload)):
            result = c.get_all_task_queues()
        assert "task_a" in result

    def test_get_all_task_queues_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_all_task_queues()
        assert isinstance(result, dict)

    def test_get_worker_last_poll_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        poll_data = [{"queueName": "t", "workerId": "w1", "lastPollTime": 123}]
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp(poll_data)):
            result = c.get_worker_last_poll("t")
        assert result[0]["workerId"] == "w1"

    def test_get_worker_last_poll_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_worker_last_poll("t")
        assert isinstance(result, list)

    def test_get_task_performance_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        now_ms = int(time.time() * 1000)
        executions = [
            {"workflowId": "w1", "status": "COMPLETED",
             "startTime": now_ms - 2000, "endTime": now_ms - 500},
            {"workflowId": "w2", "status": "FAILED",
             "startTime": now_ms - 3000, "endTime": now_ms - 2800},
        ]
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"totalHits": 2, "results": executions})):
            result = c.get_task_performance("my_task")
        assert result["totalExecutions"] == 2
        assert result["failedCount"] == 1

    def test_get_task_performance_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_task_performance("my_task")
        assert "avgDurationMs" in result

    def test_list_secrets_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp(["SECRET_A", "SECRET_B"])):
            result = c.list_secrets()
        assert "SECRET_A" in result

    def test_list_secrets_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.list_secrets()
        assert isinstance(result, list)

    def test_set_secret_live(self, monkeypatch):
        c = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("app.conductor_client.requests.put", return_value=mock_resp):
            c.set_secret("MY_KEY", "value")  # must not raise

    def test_delete_secret_live(self, monkeypatch):
        c = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("app.conductor_client.requests.delete", return_value=mock_resp):
            c.delete_secret("MY_KEY")

    def test_get_failures_by_task_type_live_success(self, monkeypatch):
        c = self._live_client(monkeypatch)
        executions = [{"workflowId": "w1", "status": "FAILED",
                       "startTime": int(time.time() * 1000) - 1000}]
        with patch("app.conductor_client.requests.get",
                   return_value=self._ok_resp({"totalHits": 1, "results": executions})):
            result = c.get_failures_by_task_type("EDA_Person_Sync")
        assert "groups" in result

    def test_get_failures_by_task_type_live_exception_falls_back(self, monkeypatch):
        c = self._live_client(monkeypatch)
        with patch("app.conductor_client.requests.get", side_effect=RuntimeError()):
            result = c.get_failures_by_task_type("EDA_Person_Sync")
        assert "groups" in result

    def test_compute_performance_no_durations(self, monkeypatch):
        """_compute_performance with all-failed executions (no valid durations)."""
        from app.conductor_client import _compute_performance
        executions = [{"status": "FAILED", "startTime": 0, "endTime": 0}]
        result = _compute_performance("my_task", executions)
        assert result["avgDurationMs"] == 0
        assert result["failedCount"] == 1

    def test_compute_performance_empty(self, monkeypatch):
        from app.conductor_client import _compute_performance
        result = _compute_performance("my_task", [])
        assert result["totalExecutions"] == 0
        assert result["successRate"] == 0


# =============================================================================
# app/routes/batches.py — all exception paths + pagination break
# =============================================================================

class TestBatchesGaps:
    def test_list_batches_db_error(self, client_with_mock_conductor):
        with patch("app.routes.batches.MigrationBatch") as MockModel:
            MockModel.query.order_by.return_value.all.side_effect = Exception("db down")
            resp = client_with_mock_conductor.get("/api/v1/batches")
        assert resp.status_code == 500

    def test_create_batch_db_error(self, client_with_mock_conductor):
        with patch("app.routes.batches.db") as mock_db:
            mock_db.session.add.side_effect = Exception("constraint violation")
            resp = client_with_mock_conductor.post("/api/v1/batches", json={
                "name": "Test", "workflowName": "EDA_Person_Sync"
            })
        assert resp.status_code == 500

    def test_batch_status_db_error(self, client_with_mock_conductor):
        with patch("app.routes.batches.MigrationBatch") as MockModel:
            MockModel.query.get.return_value = None
            MockModel.query.filter_by.return_value.first.side_effect = Exception("db error")
            resp = client_with_mock_conductor.get("/api/v1/batches/99/status")
        assert resp.status_code in (404, 500)

    def test_batch_status_conductor_error(self, client, app):
        """batch_status conductor search exception path."""
        from app.models.migration_batch import MigrationBatch
        from datetime import datetime, timezone
        with app.app_context():
            from app import db
            b = MigrationBatch(
                name="Error Batch", workflow_name="EDA_Test",
                started_at=datetime.now(timezone.utc)
            )
            db.session.add(b)
            db.session.commit()
            batch_id = b.id

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("conductor down")
            resp = client.get(f"/api/v1/batches/{batch_id}/status")
        assert resp.status_code == 500

    def test_retry_failures_conductor_error(self, client, app):
        from app.models.migration_batch import MigrationBatch
        from datetime import datetime, timezone
        with app.app_context():
            from app import db
            b = MigrationBatch(
                name="Retry Error", workflow_name="EDA_Test",
                started_at=datetime.now(timezone.utc)
            )
            db.session.add(b)
            db.session.commit()
            batch_id = b.id

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("boom")
            resp = client.post(f"/api/v1/batches/{batch_id}/retry-failures")
        assert resp.status_code == 500

    def test_export_batch_conductor_error(self, client, app):
        from app.models.migration_batch import MigrationBatch
        from datetime import datetime, timezone
        with app.app_context():
            from app import db
            b = MigrationBatch(
                name="Export Error", workflow_name="EDA_Test",
                started_at=datetime.now(timezone.utc)
            )
            db.session.add(b)
            db.session.commit()
            batch_id = b.id

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("boom")
            resp = client.get(f"/api/v1/batches/{batch_id}/export")
        assert resp.status_code == 500


# =============================================================================
# app/routes/diff.py — exception paths + empty-tasks branch
# =============================================================================

class TestDiffGaps:
    def test_list_workflows_conductor_error(self, client_with_mock_conductor):
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/diff/workflows")
        assert resp.status_code == 500

    def test_diff_workflow_conductor_error(self, client_with_mock_conductor):
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.get_workflow_definition.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.post("/api/v1/diff/workflow", json={
                "workflowName": "EDA", "versionA": 1, "versionB": 2
            })
        assert resp.status_code == 500

    def test_dependency_map_conductor_error(self, client_with_mock_conductor):
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        assert resp.status_code == 500

    def test_impact_analysis_conductor_error(self, client_with_mock_conductor):
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.post("/api/v1/diff/impact",
                                                   json={"taskType": "ethos_get_by_id"})
        assert resp.status_code == 500

    def test_dependency_map_fetches_full_def_when_tasks_empty(self, client_with_mock_conductor):
        """Hits the 'if not tasks: full = client.get_workflow_definition(...)' branch."""
        with patch("app.routes.diff.ConductorClient") as MockClient:
            mock_c = MockClient.return_value
            mock_c.list_workflow_definitions.return_value = [
                {"name": "wf_no_tasks", "version": 1, "tasks": []},
            ]
            mock_c.get_workflow_definition.return_value = {
                "name": "wf_no_tasks", "version": 1,
                "tasks": [{"name": "some_task", "taskReferenceName": "ref1", "type": "SIMPLE"}]
            }
            resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        assert resp.status_code == 200
        mock_c.get_workflow_definition.assert_called()


# =============================================================================
# app/routes/digest.py — APScheduler _job, workflow_history empty-cache, recs
# =============================================================================

class TestDigestGaps:
    def test_apscheduler_job_runs_and_delivers(self, app):
        """Drive lines 188-199: capture _job from scheduler.add_job and call it."""
        captured_job = {}

        def fake_add_job(fn, *args, **kwargs):
            captured_job["fn"] = fn

        mock_scheduler = MagicMock()
        mock_scheduler.add_job.side_effect = fake_add_job

        with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_scheduler):
            from app.routes.digest import init_scheduler
            init_scheduler(app)

        assert "fn" in captured_job
        with app.app_context():
            with patch("app.routes.digest.generate_daily_digest",
                       return_value={"date": "2026-05-18", "workflows": [],
                                     "regressions": [], "worker_health": {}}):
                with patch("app.notification_provider.deliver_digest", return_value={"channels_attempted": 0}):
                    captured_job["fn"]()  # must not raise

    def test_apscheduler_job_handles_digest_exception(self, app):
        """Lines 205-207: _job swallows generate_daily_digest exception."""
        captured_job = {}

        def fake_add_job(fn, *args, **kwargs):
            captured_job["fn"] = fn

        mock_scheduler = MagicMock()
        mock_scheduler.add_job.side_effect = fake_add_job

        with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_scheduler):
            from app.routes.digest import init_scheduler
            init_scheduler(app)

        with app.app_context():
            with patch("app.routes.digest.generate_daily_digest",
                       side_effect=RuntimeError("digest failed")):
                captured_job["fn"]()  # must not raise

    def test_recommendations_includes_regressions(self, client_with_mock_conductor):
        """Regression loop in recommendations route."""
        from app.routes import digest as digest_module
        today = digest_module._today_str()
        digest_module._digest_cache[today] = {
            "date": today,
            "workflows": [{"name": "EDA_Person_Sync", "total": 100, "trend": "up",
                           "failed": 10, "failure_rate_pct": 10.0, "avg_ms": 900}],
            "regressions": [{"workflow_name": "EDA_Person_Sync",
                             "current_avg_ms": 2000, "historical_avg_ms": 900, "pct_slower": 122}],
            "worker_health": {},
            "top_failures": [],
        }
        try:
            resp = client_with_mock_conductor.get("/api/v1/digest/recommendations")
            assert resp.status_code == 200
            recs = resp.get_json()["recommendations"]
            categories = [r["category"] for r in recs]
            assert "regression" in categories
        finally:
            digest_module._digest_cache.pop(today, None)

    def test_trend_stable_when_hist_avg_zero(self):
        """hist_avg == 0 branch in _compute_trend returns 'stable'."""
        from app.routes.digest import _compute_trend
        result = _compute_trend(500, [0, 0, 0])
        assert result == "stable"

    def test_compute_trend_empty_returns_new(self):
        """Line 74: _compute_trend([]) returns 'new'."""
        from app.routes.digest import _compute_trend
        assert _compute_trend(500, []) == "new"

    def test_scheduler_init_exception(self, app):
        """Lines 210-212: init_scheduler swallows BackgroundScheduler failure."""
        with patch("apscheduler.schedulers.background.BackgroundScheduler",
                   side_effect=RuntimeError("apscheduler broken")):
            from app.routes.digest import init_scheduler
            result = init_scheduler(app)
        assert result is None

    def test_apscheduler_deliver_digest_exception(self, app):
        """Lines 201-202: _job swallows deliver_digest exception."""
        captured_job = {}

        def fake_add_job(fn, *args, **kwargs):
            captured_job["fn"] = fn

        mock_scheduler = MagicMock()
        mock_scheduler.add_job.side_effect = fake_add_job

        with patch("apscheduler.schedulers.background.BackgroundScheduler",
                   return_value=mock_scheduler):
            from app.routes.digest import init_scheduler
            init_scheduler(app)

        with app.app_context():
            with patch("app.routes.digest.generate_daily_digest",
                       return_value={"date": "2026-05-18", "workflows": [],
                                     "regressions": [], "worker_health": {}}):
                with patch("app.notification_provider.deliver_digest",
                           side_effect=RuntimeError("webhook down")):
                    captured_job["fn"]()  # must not raise


# =============================================================================
# app/routes/jq_lab.py — ImportError, no-task-ref, empty tasks, db errors
# =============================================================================

class TestJqLabGaps:
    def test_evaluate_jq_import_error(self, client_with_mock_conductor):
        """Lines 44-45: jq library not installed → ImportError path returns 500."""
        import json as _json
        body = _json.dumps({"input": {"a": 1}, "expression": ".a"}).encode()
        with patch.dict("sys.modules", {"jq": None}):
            resp = client_with_mock_conductor.post(
                "/api/v1/jq/evaluate",
                data=body,
                content_type="application/json"
            )
        assert resp.status_code == 500

    def test_load_from_execution_no_tasks(self, client_with_mock_conductor):
        """Line 67: execution has no tasks."""
        with patch("app.routes.jq_lab.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.return_value = {
                "workflowId": "wf-empty", "tasks": []
            }
            resp = client_with_mock_conductor.get(
                "/api/v1/jq/load-from-execution?workflowId=wf-empty"
            )
        assert resp.status_code == 200
        assert resp.get_json()["found"] is False

    def test_load_from_execution_no_matching_ref_uses_last(self, client_with_mock_conductor):
        """Line 86: task_ref not found → falls back to last task."""
        with patch("app.routes.jq_lab.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.return_value = {
                "workflowId": "wf-1",
                "tasks": [{"referenceTaskName": "other_ref", "outputData": {"x": 1},
                           "taskType": "SIMPLE", "status": "COMPLETED"}]
            }
            resp = client_with_mock_conductor.get(
                "/api/v1/jq/load-from-execution?workflowId=wf-1&taskRef=nonexistent"
            )
        assert resp.status_code == 200

    def test_load_from_execution_conductor_error(self, client_with_mock_conductor):
        """Lines 102-104: conductor raises."""
        with patch("app.routes.jq_lab.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.side_effect = RuntimeError("boom")
            resp = client_with_mock_conductor.get(
                "/api/v1/jq/load-from-execution?workflowId=wf-x"
            )
        assert resp.status_code == 500

    def test_list_expressions_db_error(self, client_with_mock_conductor):
        """Lines 122-124: DB error in list_expressions."""
        with patch("app.routes.jq_lab.JqExpression") as MockModel:
            MockModel.query.order_by.return_value.all.side_effect = Exception("db")
            resp = client_with_mock_conductor.get("/api/v1/jq/expressions")
        assert resp.status_code == 500

    def test_save_expression_db_error(self, client_with_mock_conductor):
        """Lines 152-155: DB error on save."""
        with patch("app.routes.jq_lab.db") as mock_db:
            mock_db.session.add.side_effect = Exception("constraint")
            resp = client_with_mock_conductor.post("/api/v1/jq/expressions", json={
                "name": "test", "expression": ".foo", "resource_name": "persons"
            })
        assert resp.status_code == 500

    def test_format_as_conductor_task_error(self, client_with_mock_conductor):
        """Lines 182-184: exception in format — patch the module-level json ref."""
        import json as _json
        body = _json.dumps({"expression": ".x", "taskName": "my_task"}).encode()
        with patch("app.routes.jq_lab.json") as mock_json:
            mock_json.dumps.side_effect = Exception("boom")
            resp = client_with_mock_conductor.post(
                "/api/v1/jq/format-as-conductor-task",
                data=body,
                content_type="application/json"
            )
        assert resp.status_code == 500


# =============================================================================
# app/routes/reconciler.py — HTTP error code extraction, exception paths
# =============================================================================

class TestReconcilerGaps:
    def test_extract_error_code_numeric_http(self, client):
        """Line 51: leading numeric HTTP code (e.g. '404 Not Found')."""
        from app.routes.reconciler import _extract_error_code
        assert _extract_error_code("404 Not Found") == "HTTP_404"
        assert _extract_error_code("500 Internal Server Error") == "HTTP_500"

    def test_list_failures_conductor_error(self, client_with_mock_conductor):
        """Lines 104-106."""
        with patch("app.routes.reconciler.ConductorClient") as MockClient:
            MockClient.return_value.get_failures_by_task_type.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get(
                "/api/v1/reconciler/failures?workflow_name=EDA_Person_Sync"
            )
        assert resp.status_code == 500

    def test_get_failure_detail_no_failed_task_uses_last(self, client_with_mock_conductor):
        """Line 125: no FAILED task → uses last task."""
        with patch("app.routes.reconciler.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.return_value = {
                "workflowId": "wf-x", "status": "TIMED_OUT",
                "tasks": [
                    {"taskType": "ethos_get_by_id", "status": "COMPLETED",
                     "referenceTaskName": "ref1", "reasonForIncompletion": None,
                     "startTime": 1000, "endTime": 2000, "retried": False}
                ]
            }
            resp = client_with_mock_conductor.get("/api/v1/reconciler/failures/wf-x")
        assert resp.status_code == 200

    def test_get_failure_detail_conductor_error(self, client_with_mock_conductor):
        """Lines 160-162."""
        with patch("app.routes.reconciler.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/reconciler/failures/wf-bad")
        assert resp.status_code == 500

    def test_bulk_retry_empty_list(self, client_with_mock_conductor):
        """Line 176: empty workflow_ids."""
        resp = client_with_mock_conductor.post(
            "/api/v1/reconciler/failures/bulk-retry",
            json={"workflow_ids": []}
        )
        assert resp.status_code == 400

    def test_bulk_retry_individual_retry_exception(self, client_with_mock_conductor):
        """Lines 190-191: one retry raises, rest succeed."""
        with patch("app.routes.reconciler.ConductorClient") as MockClient:
            MockClient.return_value.retry_workflow.side_effect = RuntimeError("retry failed")
            resp = client_with_mock_conductor.post(
                "/api/v1/reconciler/failures/bulk-retry",
                json={"workflow_ids": ["wf-001", "wf-002"]}
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["errors"]

    def test_failure_summary_conductor_error(self, client_with_mock_conductor):
        """Lines 256-258."""
        with patch("app.routes.reconciler.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/reconciler/summary")
        assert resp.status_code == 500


# =============================================================================
# app/routes/search.py — not_exists operator, db error paths
# =============================================================================

class TestSearchGaps:
    def test_filter_not_exists_operator_missing_field(self, client_with_mock_conductor):
        """Line 62: not_exists operator when field IS present (should exclude)."""
        from app.routes.search import _matches_filter
        result = {"orderId": 1001, "status": "COMPLETED"}
        assert _matches_filter(result, [{"path": "orderId", "operator": "not_exists", "value": ""}]) is False

    def test_filter_not_exists_operator_absent_field(self, client_with_mock_conductor):
        """not_exists on field that is absent → should match."""
        from app.routes.search import _matches_filter
        result = {"input": json.dumps({"orderId": 1001})}
        assert _matches_filter(result, [{"path": "missingField", "operator": "not_exists", "value": ""}]) is True

    def test_list_saved_searches_db_error(self, client_with_mock_conductor):
        """Lines 121-123."""
        with patch("app.routes.search.SavedSearch") as MockModel:
            MockModel.query.order_by.return_value.all.side_effect = Exception("db")
            resp = client_with_mock_conductor.get("/api/v1/search/saved")
        assert resp.status_code == 500

    def test_create_saved_search_db_error(self, client_with_mock_conductor):
        """Lines 144-147."""
        with patch("app.routes.search.db") as mock_db:
            mock_db.session.add.side_effect = Exception("constraint")
            resp = client_with_mock_conductor.post("/api/v1/search/saved", json={
                "name": "My Search", "search_config": {"status": "FAILED"}
            })
        assert resp.status_code == 500

    def test_delete_saved_search_db_error(self, client_with_mock_conductor, app):
        """Lines 160-163."""
        from app.models.saved_search import SavedSearch
        with app.app_context():
            from app import db as _db
            s = SavedSearch(name="del test", search_config={"q": "x"})
            _db.session.add(s)
            _db.session.commit()
            sid = s.id

        with patch("app.routes.search.db") as mock_db:
            mock_db.session.get.side_effect = Exception("db")
            resp = client_with_mock_conductor.delete(f"/api/v1/search/saved/{sid}")
        assert resp.status_code == 500

    def test_export_csv_conductor_error(self, client_with_mock_conductor):
        """Lines 208-210."""
        with patch("app.routes.search.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.post("/api/v1/search/export", json={
                "workflowType": "EDA_Person_Sync"
            })
        assert resp.status_code == 500


# =============================================================================
# app/routes/secrets.py — seen-set dedup + exception paths
# =============================================================================

class TestSecretsGaps:
    def test_usages_deduplicates_same_workflow_version(self, client_with_mock_conductor):
        """Line 76: seen-set skips duplicate key."""
        with patch("app.routes.secrets.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.return_value = [
                {"name": "EDA_Sync", "version": 1,
                 "tasks": [{"inputParameters": {"x": "${workflow.secrets.MY_KEY}"}}]},
                {"name": "EDA_Sync", "version": 1,
                 "tasks": [{"inputParameters": {"x": "${workflow.secrets.MY_KEY}"}}]},
            ]
            resp = client_with_mock_conductor.get("/api/v1/secrets/MY_KEY/usages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["usageCount"] == 1  # deduplicated

    def test_usages_conductor_error(self, client_with_mock_conductor):
        """Lines 111-113."""
        with patch("app.routes.secrets.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/secrets/MY_KEY/usages")
        assert resp.status_code == 500


# =============================================================================
# app/routes/sf_console.py — empty identifier
# =============================================================================

class TestSfConsoleGaps:
    def test_get_person_empty_identifier(self, client_with_mock_conductor):
        """Line 36: empty identifier after strip."""
        resp = client_with_mock_conductor.get("/api/v1/sf/person/%20")
        assert resp.status_code == 400


# =============================================================================
# app/routes/tracer.py — missing start_ms, ethos filter skip, error paths
# =============================================================================

class TestTracerGaps:
    def test_build_timeline_no_start_ms(self, client_with_mock_conductor):
        """Line 80: execution missing startTime → falls back to _now_iso()."""
        with patch("app.routes.tracer.ConductorClient") as MockClient:
            MockClient.return_value.search.return_value = {
                "results": [{"workflowId": "wf-no-ts", "workflowType": "EDA",
                             "status": "COMPLETED", "startTime": None, "endTime": None}]
            }
            resp = client_with_mock_conductor.post(
                "/api/v1/tracer/person", json={"sis_id": "STU99"}
            )
        assert resp.status_code == 200

    def test_build_timeline_ethos_event_filtered_out(self, client_with_mock_conductor):
        """Line 132: ethos event not matching identifier → skip."""
        from app import ethos_provider
        ethos_provider._event_buffer.clear()
        ethos_provider.ingest_event({
            "resource": "persons", "id": "different-guid", "operation": "updated",
            "content": "unrelated content"
        })
        with patch("app.routes.tracer.ConductorClient") as MockClient:
            MockClient.return_value.search.return_value = {"results": []}
            resp = client_with_mock_conductor.post(
                "/api/v1/tracer/person", json={"sis_id": "STU12345"}
            )
        assert resp.status_code == 200
        trace = resp.get_json()["trace"]
        ethos_events = [e for e in trace if e["system"] == "ETHOS"]
        assert len(ethos_events) == 0

    def test_trace_person_conductor_error(self, client_with_mock_conductor):
        """Lines 209-211."""
        with patch("app.routes.tracer.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.post(
                "/api/v1/tracer/person", json={"sis_id": "STU1"}
            )
        assert resp.status_code == 500

    def test_trace_person_get_empty_identifier(self, client_with_mock_conductor):
        """Line 228: GET with empty identifier after strip."""
        resp = client_with_mock_conductor.get("/api/v1/tracer/person/%20")
        assert resp.status_code == 400

    def test_trace_person_get_conductor_error(self, client_with_mock_conductor):
        """Lines 276-278."""
        with patch("app.routes.tracer.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/tracer/person/STU99")
        assert resp.status_code == 500


# =============================================================================
# app/routes/workers.py — exception paths
# =============================================================================

class TestWorkersGaps:
    def test_worker_status_conductor_error(self, client_with_mock_conductor):
        """Lines 104-106."""
        with patch("app.routes.workers.ConductorClient") as MockClient:
            MockClient.return_value.get_all_task_queues.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/workers/status")
        assert resp.status_code == 500

    def test_worker_performance_conductor_error(self, client_with_mock_conductor):
        """Lines 116-118."""
        with patch("app.routes.workers.ConductorClient") as MockClient:
            MockClient.return_value.get_task_performance.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get(
                "/api/v1/workers/validate_order/performance"
            )
        assert resp.status_code == 500


# =============================================================================
# app/routes/test_harness.py — live POST path, exception paths
# =============================================================================

class TestHarnessGaps:
    def test_list_workflows_error(self, client_with_mock_conductor):
        """Lines 235-237."""
        with patch("app.routes.test_harness.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get("/api/v1/test-harness/workflows")
        assert resp.status_code == 500

    def test_get_workflow_tasks_error(self, client_with_mock_conductor):
        """Lines 272-274."""
        with patch("app.routes.test_harness.ConductorClient") as MockClient:
            MockClient.return_value.get_workflow_definition.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.get(
                "/api/v1/test-harness/workflows/EDA_Person_Sync/tasks"
            )
        assert resp.status_code == 500

    def test_run_test_live_mode(self, monkeypatch, client):
        """Lines 312-337: live POST to /api/workflow/test when CONDUCTOR_URL set."""
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor.test")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "workflowId": "live-test-id", "status": "COMPLETED", "tasks": []
        }

        with patch("app.routes.test_harness.ConductorClient") as MockClient:
            MockClient.return_value._mock_mode = False
            MockClient.return_value.base_url = "http://conductor.test"
            MockClient.return_value.get_headers.return_value = {}
            with patch("requests.post", return_value=mock_resp):
                resp = client.post("/api/v1/test-harness/run", json={
                    "workflow_name": "EDA_Person_Sync",
                    "version": 1,
                    "input": {"personId": "STU1"},
                    "task_mocks": {}
                })
        assert resp.status_code == 200

    def test_run_test_error(self, client_with_mock_conductor):
        """Lines 334-337: run raises."""
        with patch("app.routes.test_harness.ConductorClient") as MockClient:
            MockClient.return_value.get_workflow_definition.side_effect = RuntimeError("down")
            resp = client_with_mock_conductor.post("/api/v1/test-harness/run", json={
                "workflow_name": "EDA_Person_Sync", "version": 1,
                "input": {}, "task_mocks": {}
            })
        assert resp.status_code == 500

    def test_get_presets_error(self, client_with_mock_conductor):
        """Lines 364-366."""
        with patch("app.routes.test_harness.TestPreset") as MockModel:
            MockModel.query.order_by.return_value.all.side_effect = Exception("db")
            resp = client_with_mock_conductor.get("/api/v1/test-harness/presets")
        assert resp.status_code == 500

    def test_save_preset_db_error(self, client_with_mock_conductor):
        """Lines 395-398."""
        with patch("app.routes.test_harness.db") as mock_db:
            mock_db.session.add.side_effect = Exception("constraint")
            resp = client_with_mock_conductor.post("/api/v1/test-harness/presets", json={
                "name": "My Preset", "workflow_name": "EDA_Person_Sync",
                "input_data": {}, "task_mocks": {}
            })
        assert resp.status_code == 500

    def test_simulate_execution_with_output_params(self, client_with_mock_conductor):
        """Lines 188-191: outputParameters triggers workflow output assembly."""
        with patch("app.routes.test_harness.ConductorClient") as MockClient:
            MockClient.return_value._mock_mode = True
            MockClient.return_value.get_workflow_definition.return_value = {
                "name": "EDA_Person_Sync",
                "tasks": [
                    {"name": "fetch_person", "taskReferenceName": "fetch_ref",
                     "type": "SIMPLE"}
                ],
                "outputParameters": {"personId": "${fetch_ref.personId}"},
            }
            resp = client_with_mock_conductor.post("/api/v1/test-harness/run", json={
                "workflow_name": "EDA_Person_Sync",
                "version": 1,
                "input": {},
                "task_mocks": {"fetch_ref": {"outputData": {"personId": "STU123"}}}
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "fetch_ref.personId" in data.get("output", {})


# =============================================================================
# Remaining coverage gaps — added in second pass
# =============================================================================

class TestConductorClientGroupFailures:
    """Cover _group_failures_by_task_type lines 606-608, 610, 620."""

    def test_group_failures_failed_task_found(self):
        """Lines 606-608: task with status=FAILED sets failed_task."""
        from app.conductor_client import _group_failures_by_task_type
        executions = [{
            "workflowId": "wf-1",
            "tasks": [
                {"status": "COMPLETED", "taskType": "fetch", "reasonForIncompletion": ""},
                {"status": "FAILED", "taskType": "ethos_sync", "reasonForIncompletion": "timeout"},
            ]
        }]
        result = _group_failures_by_task_type(executions, "EDA")
        assert result["total_failures"] == 1
        assert result["groups"][0]["task_type"] == "ethos_sync"

    def test_group_failures_no_failed_task_uses_last(self):
        """Line 610: no FAILED task → falls back to tasks[-1]."""
        from app.conductor_client import _group_failures_by_task_type
        executions = [{
            "workflowId": "wf-2",
            "tasks": [{"status": "RUNNING", "taskType": "long_running", "reasonForIncompletion": ""}]
        }]
        result = _group_failures_by_task_type(executions, "EDA")
        assert result["groups"][0]["task_type"] == "long_running"

    def test_group_failures_records_reason(self):
        """Line 620: reason string is recorded in reasons map."""
        from app.conductor_client import _group_failures_by_task_type
        executions = [{
            "workflowId": "wf-3",
            "tasks": [{"status": "FAILED", "taskType": "fetch",
                       "reasonForIncompletion": "Connection refused"}]
        }]
        result = _group_failures_by_task_type(executions, "EDA")
        reasons = result["groups"][0]["reasons"]
        assert "Connection refused" in reasons


class TestConductorClientExceptionHandlers:
    """Cover exception-handler fallbacks in get_task_performance and get_failures_by_task_type."""

    def _live_client(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "http://conductor.test")
        monkeypatch.delenv("CONDUCTOR_API_KEY", raising=False)
        from app.conductor_client import ConductorClient
        return ConductorClient()

    def test_get_task_performance_search_raises(self, monkeypatch):
        """Lines 235-236: search raises → falls back to mock."""
        c = self._live_client(monkeypatch)
        with patch.object(c, "search", side_effect=RuntimeError("search error")):
            result = c.get_task_performance("my_task")
        assert "avgDurationMs" in result

    def test_get_failures_by_task_type_search_raises(self, monkeypatch):
        """Lines 263-264: search raises → falls back to mock."""
        c = self._live_client(monkeypatch)
        with patch.object(c, "search", side_effect=RuntimeError("search error")):
            result = c.get_failures_by_task_type("EDA_Person_Sync")
        assert "groups" in result


class TestBatchesPagination:
    """Cover pagination next-page lines: 88 (status), 157 (retry), 197 (export)."""

    def _make_batch(self, app):
        from app.models.migration_batch import MigrationBatch
        with app.app_context():
            from app import db
            b = MigrationBatch(name="Page Batch", workflow_name="EDA_Test")
            db.session.add(b)
            db.session.commit()
            return b.id

    def test_batch_status_pagination_continues(self, client, app):
        """Line 88: full first page triggers start += page_size."""
        batch_id = self._make_batch(app)
        page1 = [{"workflowId": f"wf-{i}", "status": "COMPLETED"} for i in range(100)]
        page2 = [{"workflowId": "wf-last", "status": "FAILED"}]
        calls = [0]

        def mock_search(**kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return {"results": page1, "totalHits": 101}
            return {"results": page2, "totalHits": 101}

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = mock_search
            resp = client.get(f"/api/v1/batches/{batch_id}/status")
        assert resp.status_code == 200
        assert resp.get_json()["totalFound"] == 101

    def test_retry_failures_pagination_continues(self, client, app):
        """Line 157: full first page triggers start += page_size in retry."""
        batch_id = self._make_batch(app)
        page1 = [{"workflowId": f"wf-{i}"} for i in range(100)]
        page2 = [{"workflowId": "wf-last"}]
        calls = [0]

        def mock_search(**kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return {"results": page1, "totalHits": 101}
            return {"results": page2, "totalHits": 101}

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = mock_search
            MockClient.return_value.retry_workflow.return_value = None
            resp = client.post(f"/api/v1/batches/{batch_id}/retry-failures")
        assert resp.status_code == 200
        assert resp.get_json()["retriedCount"] == 101

    def test_retry_failures_individual_exception(self, client, app):
        """Lines 152-153: retry_workflow raises for one ID → errors list."""
        batch_id = self._make_batch(app)
        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.return_value = {
                "results": [{"workflowId": "wf-will-fail"}], "totalHits": 1
            }
            MockClient.return_value.retry_workflow.side_effect = RuntimeError("retry refused")
            resp = client.post(f"/api/v1/batches/{batch_id}/retry-failures")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["errorCount"] == 1

    def test_export_batch_pagination_continues(self, client, app):
        """Line 197: full first page triggers start += page_size in export."""
        batch_id = self._make_batch(app)
        page1 = [{"workflowId": f"wf-{i}", "status": "FAILED",
                  "workflowType": "EDA_Test", "correlationId": "",
                  "startTime": 0, "endTime": 0, "version": 1} for i in range(100)]
        page2 = [{"workflowId": "wf-last", "status": "FAILED",
                  "workflowType": "EDA_Test", "correlationId": "",
                  "startTime": 0, "endTime": 0, "version": 1}]
        calls = [0]

        def mock_search(**kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return {"results": page1, "totalHits": 101}
            return {"results": page2, "totalHits": 101}

        with patch("app.routes.batches.ConductorClient") as MockClient:
            MockClient.return_value.search.side_effect = mock_search
            resp = client.get(f"/api/v1/batches/{batch_id}/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type


class TestDiffGaps2:
    """Cover remaining diff.py gaps: dedup continues, impact_analysis empty tasks."""

    def test_dependency_map_dedup_skips_duplicate(self, client_with_mock_conductor):
        """Line 149: duplicate key skipped in dependency_map."""
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.return_value = [
                {"name": "wf_dup", "version": 1,
                 "tasks": [{"name": "task1", "taskReferenceName": "t1"}]},
                {"name": "wf_dup", "version": 1,
                 "tasks": [{"name": "task1", "taskReferenceName": "t1"}]},
            ]
            resp = client_with_mock_conductor.get("/api/v1/diff/dependency-map")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["totalWorkflows"] == 1  # duplicate deduplicated

    def test_impact_analysis_empty_tasks_fetches_full(self, client_with_mock_conductor):
        """Lines 200-201: impact_analysis fetches full def when tasks empty."""
        with patch("app.routes.diff.ConductorClient") as MockClient:
            mock_c = MockClient.return_value
            mock_c.list_workflow_definitions.return_value = [
                {"name": "wf_no_tasks", "version": 1, "tasks": []},
            ]
            mock_c.get_workflow_definition.return_value = {
                "name": "wf_no_tasks", "version": 1,
                "tasks": [{"name": "ethos_get", "taskReferenceName": "ethos_ref"}]
            }
            resp = client_with_mock_conductor.post("/api/v1/diff/impact",
                                                   json={"taskType": "ethos_get"})
        assert resp.status_code == 200
        mock_c.get_workflow_definition.assert_called()

    def test_impact_analysis_dedup_skips_duplicate(self, client_with_mock_conductor):
        """Line 195: duplicate key skipped in impact_analysis."""
        with patch("app.routes.diff.ConductorClient") as MockClient:
            MockClient.return_value.list_workflow_definitions.return_value = [
                {"name": "wf_dup", "version": 1,
                 "tasks": [{"name": "ethos_get", "taskReferenceName": "ref1"}]},
                {"name": "wf_dup", "version": 1,
                 "tasks": [{"name": "ethos_get", "taskReferenceName": "ref1"}]},
            ]
            resp = client_with_mock_conductor.post("/api/v1/diff/impact",
                                                   json={"taskType": "ethos_get"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["impactedWorkflows"]) == 1  # deduplicated


class TestJqLabEvaluateOuterException:
    """Line 46-48: outer except Exception in evaluate()."""

    def test_evaluate_outer_exception_via_json_loads(self, client_with_mock_conductor):
        """Lines 46-48: unexpected RuntimeError in json.loads bubbles to outer except."""
        import json as _json
        from types import SimpleNamespace
        body = _json.dumps({"expression": ".a", "input": '{"a":1}'}).encode()
        fake_json = SimpleNamespace(
            JSONDecodeError=_json.JSONDecodeError,
            loads=MagicMock(side_effect=RuntimeError("unexpected parse error")),
        )
        with patch("app.routes.jq_lab.json", fake_json):
            resp = client_with_mock_conductor.post(
                "/api/v1/jq/evaluate",
                data=body,
                content_type="application/json"
            )
        assert resp.status_code == 500


class TestJqLabFallbackToLastTask:
    """Line 86: fallback to tasks[-1] when no COMPLETED task and no taskRef."""

    def test_load_from_execution_fallback_to_last_task(self, client_with_mock_conductor):
        """Line 86: no taskRef, no COMPLETED task → uses tasks[-1]."""
        with patch("app.routes.jq_lab.ConductorClient") as MockClient:
            MockClient.return_value.get_execution.return_value = {
                "workflowId": "wf-running",
                "tasks": [{"referenceTaskName": "ref1", "outputData": {"x": 99},
                           "taskType": "SIMPLE", "status": "RUNNING",
                           "taskId": "t-abc"}]
            }
            resp = client_with_mock_conductor.get(
                "/api/v1/jq/load-from-execution?workflowId=wf-running"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["found"] is True
        assert data["data"]["x"] == 99


class TestReconcilerNotAList:
    """Line 176: workflow_ids must be an array."""

    def test_bulk_retry_not_a_list(self, client_with_mock_conductor):
        """Line 176: workflow_ids is a string → 400."""
        resp = client_with_mock_conductor.post(
            "/api/v1/reconciler/failures/bulk-retry",
            json={"workflow_ids": "not-a-list"}
        )
        assert resp.status_code == 400


class TestTracerEthosEventMatches:
    """Line 132: ethos event that matches identifier is appended to timeline."""

    def test_build_timeline_ethos_event_matches(self, client_with_mock_conductor):
        """Line 132: event content contains identifier → appended, not skipped."""
        matching_event = {
            "resource": "persons",
            "id": "STU12345-guid",
            "operation": "updated",
            "content": "STU12345 record updated",
            "received_at": "2026-05-18T00:00:00+00:00",
        }
        with patch("app.routes.tracer.ethos_provider.get_recent_events",
                   return_value=[matching_event]):
            resp = client_with_mock_conductor.post(
                "/api/v1/tracer/person", json={"sis_id": "STU12345"}
            )
        assert resp.status_code == 200
        trace = resp.get_json()["trace"]
        ethos_events = [e for e in trace if e["system"] == "ETHOS"]
        assert len(ethos_events) >= 1
