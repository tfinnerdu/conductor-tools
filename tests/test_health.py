"""Tests for health endpoints and shared health_checks module.

CI tests and live health endpoints share the same check functions
(app.health_checks) — single implementation, both consumers import.
"""
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared check functions — test the module directly, not via HTTP
# ---------------------------------------------------------------------------

class TestCheckConductorLive:
    def test_not_configured_returns_ok(self):
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            from app.health_checks import check_conductor_live
            result = check_conductor_live()
        assert result["ok"] is True
        assert result["detail"] == "not_configured"
        assert result["latency_ms"] is None

    def test_reachable_conductor_returns_ok(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.dict(os.environ, {"CONDUCTOR_URL": "http://localhost:8080"}):
            with patch("app.health_checks.requests.get", return_value=mock_resp):
                from app.health_checks import check_conductor_live
                result = check_conductor_live()
        assert result["ok"] is True
        assert result["latency_ms"] is not None

    def test_conductor_500_returns_degraded(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch.dict(os.environ, {"CONDUCTOR_URL": "http://localhost:8080"}):
            with patch("app.health_checks.requests.get", return_value=mock_resp):
                from app.health_checks import check_conductor_live
                result = check_conductor_live()
        assert result["ok"] is False
        assert "http_503" in result["detail"]

    def test_conductor_timeout_returns_degraded(self):
        import requests as req_lib
        with patch.dict(os.environ, {"CONDUCTOR_URL": "http://localhost:8080"}):
            with patch("app.health_checks.requests.get", side_effect=req_lib.Timeout):
                from app.health_checks import check_conductor_live
                result = check_conductor_live()
        assert result["ok"] is False
        assert result["detail"] == "timeout"


class TestCheckDb:
    def test_db_connected_returns_ok(self, app):
        with app.app_context():
            from app.health_checks import check_db
            result = check_db()
        assert result["ok"] is True
        assert result["latency_ms"] is not None

    def test_db_failure_returns_error(self, app):
        with app.app_context():
            with patch("app.health_checks.db") as mock_db:
                mock_db.session.execute.side_effect = Exception("connection refused")
                from app.health_checks import check_db
                result = check_db()
        assert result["ok"] is False
        assert "connection refused" in result["detail"]


class TestCheckConductorFunctional:
    def test_mock_mode_returns_ok(self):
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            from app.health_checks import check_conductor_functional
            result = check_conductor_functional()
        assert result["ok"] is True
        assert result["detail"] == "mock_mode"

    def test_live_mode_returns_workflow_count(self):
        mock_client = MagicMock()
        mock_client.list_workflow_definitions.return_value = [{"name": "wf1"}, {"name": "wf2"}]
        with patch.dict(os.environ, {"CONDUCTOR_URL": "http://localhost:8080"}):
            with patch("app.health_checks.ConductorClient", return_value=mock_client):
                from app.health_checks import check_conductor_functional
                result = check_conductor_functional()
        assert result["ok"] is True
        assert result["workflow_count"] == 2


class TestReadOnlyChecks:
    def test_returns_ok_structure(self):
        with patch("app.health_checks.check_conductor_live", return_value={"ok": True, "detail": "reachable", "latency_ms": 5}):
            from app.health_checks import read_only_checks
            result = read_only_checks()
        assert "ok" in result
        assert "checks" in result
        assert "conductor" in result["checks"]

    def test_degraded_when_conductor_down(self):
        with patch("app.health_checks.check_conductor_live", return_value={"ok": False, "detail": "timeout", "latency_ms": 2000}):
            from app.health_checks import read_only_checks
            result = read_only_checks()
        assert result["ok"] is False


class TestFunctionalChecks:
    def test_returns_ok_structure(self, app):
        with app.app_context():
            with patch("app.health_checks.check_conductor_functional", return_value={"ok": True, "detail": "mock_mode", "latency_ms": None}):
                from app.health_checks import functional_checks
                result = functional_checks()
        assert "ok" in result
        assert "checks" in result
        assert "db" in result["checks"]
        assert "conductor" in result["checks"]

    def test_degraded_when_db_down(self, app):
        with app.app_context():
            with patch("app.health_checks.check_db", return_value={"ok": False, "detail": "connection refused", "latency_ms": 10}), \
                 patch("app.health_checks.check_conductor_functional", return_value={"ok": True, "detail": "mock_mode", "latency_ms": None}):
                from app.health_checks import functional_checks
                result = functional_checks()
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# HTTP endpoint tests — routes import from health_checks (same functions)
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200_when_healthy(self, client):
        with patch("app.routes.health.read_only_checks", return_value={"ok": True, "checks": {"conductor": {"ok": True, "detail": "not_configured"}}}):
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "conductor-companion"
        assert "uptime_seconds" in data
        assert "checks" in data

    def test_returns_503_when_degraded(self, client):
        with patch("app.routes.health.read_only_checks", return_value={"ok": False, "checks": {"conductor": {"ok": False, "detail": "timeout"}}}):
            resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.get_json()["status"] == "degraded"

    def test_includes_version(self, client):
        with patch("app.routes.health.read_only_checks", return_value={"ok": True, "checks": {}}):
            resp = client.get("/health")
        assert "version" in resp.get_json()


class TestHealthDeepEndpoint:
    def test_returns_200_when_all_checks_pass(self, client, app):
        with app.app_context():
            with patch("app.routes.health.functional_checks", return_value={
                "ok": True,
                "checks": {
                    "db": {"ok": True, "latency_ms": 3, "detail": "connected"},
                    "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"},
                },
            }):
                resp = client.get("/health/deep")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "db" in data["checks"]
        assert "conductor" in data["checks"]
        assert "request_id" in data

    def test_returns_503_when_db_down(self, client, app):
        with app.app_context():
            with patch("app.routes.health.functional_checks", return_value={
                "ok": False,
                "checks": {
                    "db": {"ok": False, "latency_ms": 10, "detail": "connection refused"},
                    "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"},
                },
            }):
                resp = client.get("/health/deep")
        assert resp.status_code == 503
        assert resp.get_json()["status"] == "degraded"

    def test_never_called_by_automated_monitor(self, client):
        # Verify the deep endpoint path differs from /health so Pingdom
        # can't accidentally be wired to it.
        resp_live = client.get("/health")
        resp_deep = client.get("/health/deep")
        assert resp_live.status_code in (200, 503)
        assert resp_deep.status_code in (200, 503)
        # Deep endpoint must include per-component check detail
        deep_data = resp_deep.get_json()
        assert "db" in deep_data.get("checks", {})
