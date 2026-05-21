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
# HTTP endpoint tests — /api/v1/health and /api/v1/health/deep
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200_always(self, client):
        """Liveness must always return 200 — it is never 503."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_status_is_always_ok(self, client):
        """Liveness status string must be 'ok' with no exceptions."""
        resp = client.get("/api/v1/health")
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_required_body_keys(self, client):
        """Liveness body must include exactly status, service, version, uptime_seconds."""
        resp = client.get("/api/v1/health")
        data = resp.get_json()
        for key in ("status", "service", "version", "uptime_seconds"):
            assert key in data, f"Missing required key: {key}"

    def test_service_name(self, client):
        resp = client.get("/api/v1/health")
        assert resp.get_json()["service"] == "conductor-companion"

    def test_uptime_seconds_is_integer(self, client):
        resp = client.get("/api/v1/health")
        assert isinstance(resp.get_json()["uptime_seconds"], int)

    def test_no_checks_key_in_liveness(self, client):
        """Liveness must NOT include a 'checks' key — that belongs to /deep."""
        resp = client.get("/api/v1/health")
        assert "checks" not in resp.get_json()

    def test_legacy_path_redirects_308(self, client):
        """Bare /health must 308-redirect to /api/v1/health (transition shim)."""
        resp = client.get("/health")
        assert resp.status_code == 308
        assert "/api/v1/health" in resp.headers.get("Location", "")

    def test_version_present(self, client):
        resp = client.get("/api/v1/health")
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
                resp = client.get("/api/v1/health/deep")
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
                resp = client.get("/api/v1/health/deep")
        assert resp.status_code == 503
        assert resp.get_json()["status"] == "degraded"

    def test_mock_key_present_in_mock_mode(self, client):
        """Deep health must include 'mock' key — required for mock/live signal."""
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            with patch("app.routes.health.functional_checks", return_value={
                "ok": True, "checks": {"db": {"ok": True, "latency_ms": 1, "detail": "connected"},
                                       "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"}},
            }):
                resp = client.get("/api/v1/health/deep")
        data = resp.get_json()
        assert "mock" in data, "Deep health must include 'mock' key"
        assert data["mock"] is True  # CONDUCTOR_URL is empty → mock mode

    def test_mock_is_false_when_live(self, client):
        with patch.dict(os.environ, {"CONDUCTOR_URL": "http://conductor.doane.edu"}):
            with patch("app.routes.health.functional_checks", return_value={
                "ok": True, "checks": {"db": {"ok": True, "latency_ms": 1, "detail": "connected"},
                                       "conductor": {"ok": True, "latency_ms": 10, "detail": "reachable"}},
            }):
                resp = client.get("/api/v1/health/deep")
        assert resp.get_json()["mock"] is False

    def test_legacy_deep_path_redirects_308(self, client):
        """Bare /health/deep must 308-redirect (transition shim)."""
        resp = client.get("/health/deep")
        assert resp.status_code == 308
        assert "/api/v1/health/deep" in resp.headers.get("Location", "")

    def test_paths_are_distinct(self, client):
        """Liveness and readiness must be on distinct paths."""
        live_resp = client.get("/api/v1/health")
        deep_resp = client.get("/api/v1/health/deep")
        assert live_resp.status_code == 200
        assert deep_resp.status_code in (200, 503)
        deep_data = deep_resp.get_json()
        assert "db" in deep_data.get("checks", {}), "Deep endpoint must include per-component check detail"
