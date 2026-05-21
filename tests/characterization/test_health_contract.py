"""Characterization tests — Health Endpoint Contract.

Pins:
  - Exact URL paths: /api/v1/health and /api/v1/health/deep
  - Required response keys for each endpoint
  - status value for liveness is exactly "ok" (never "healthy", never "up")
  - /api/v1/health always returns HTTP 200 (liveness invariant)
  - /api/v1/health/deep includes "mock" key and "checks" dict
  - /api/v1/health/deep returns 503 when checks["ok"] is False

If any of these assertions fail due to an intentional change, update the
hardcoded values AND update this comment to record when and why.
Last verified: 2026-05-21 (console audit v2).
"""
import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Known-good path contract
# ---------------------------------------------------------------------------

KNOWN_LIVENESS_PATH = "/api/v1/health"
KNOWN_READINESS_PATH = "/api/v1/health/deep"
KNOWN_LIVENESS_STATUS_STRING = "ok"
KNOWN_SERVICE_NAME = "conductor-companion"
KNOWN_LIVENESS_REQUIRED_KEYS = {"status", "service", "version", "uptime_seconds"}
KNOWN_READINESS_REQUIRED_KEYS = {"status", "service", "version", "uptime_seconds", "mock", "checks"}


class TestLivenessPathCharacterization:
    """Characterization: liveness endpoint path and response shape."""

    def test_liveness_path_is_versioned_characterization(self, client):
        """
        CONTRACT: liveness endpoint lives at /api/v1/health.
        If this path changes, monitoring configs (Pingdom, Uptime Kuma,
        hub-service, k8s probes) must be updated in the same commit.
        """
        resp = client.get(KNOWN_LIVENESS_PATH)
        assert resp.status_code == 200, (
            f"Liveness path has changed or is broken. "
            f"Known-good path is '{KNOWN_LIVENESS_PATH}'. "
            f"Got status {resp.status_code}. "
            f"Update monitoring config before changing this path."
        )

    def test_liveness_always_200_characterization(self, client):
        """
        CONTRACT: /api/v1/health returns HTTP 200 unconditionally.
        Liveness = process alive. It is never 503. If this changes,
        Pingdom will start firing false-positive alerts on dependency downtime.
        """
        resp = client.get(KNOWN_LIVENESS_PATH)
        assert resp.status_code == 200, (
            f"Liveness returned {resp.status_code}. "
            "Liveness must always return 200 — it must not probe dependencies. "
            "If you need dep probes, use /api/v1/health/deep."
        )

    def test_liveness_status_string_is_ok_characterization(self, client):
        """
        CONTRACT: status field must be exactly the string 'ok'.
        Not 'healthy', not 'up', not 'running'. Monitoring tools parse
        this value by exact string match.
        """
        resp = client.get(KNOWN_LIVENESS_PATH)
        data = resp.get_json()
        assert data.get("status") == KNOWN_LIVENESS_STATUS_STRING, (
            f"Liveness status must be '{KNOWN_LIVENESS_STATUS_STRING}', "
            f"got '{data.get('status')}'. "
            "Monitoring tools depend on this exact string."
        )

    def test_liveness_required_keys_characterization(self, client):
        """
        CONTRACT: liveness body must contain exactly these four keys.
        Adding keys is OK. Removing any of the four is a breaking change
        for monitoring consumers.
        """
        resp = client.get(KNOWN_LIVENESS_PATH)
        data = resp.get_json()
        missing = KNOWN_LIVENESS_REQUIRED_KEYS - set(data.keys())
        assert not missing, (
            f"Liveness response is missing required keys: {missing}. "
            f"Known-good required keys: {KNOWN_LIVENESS_REQUIRED_KEYS}. "
            "Update monitoring consumers before removing keys."
        )

    def test_liveness_has_no_dependency_checks_characterization(self, client):
        """
        CONTRACT: liveness must NOT include a 'checks' dict.
        That belongs in /deep. If 'checks' appears in liveness, dependency
        probes have leaked into the polling-safe endpoint.
        """
        resp = client.get(KNOWN_LIVENESS_PATH)
        data = resp.get_json()
        assert "checks" not in data, (
            "Liveness response unexpectedly contains 'checks'. "
            "Dependency probes must only appear in /api/v1/health/deep. "
            "Liveness must not probe dependencies."
        )


class TestReadinessPathCharacterization:
    """Characterization: readiness endpoint path and response shape."""

    def test_readiness_path_is_versioned_characterization(self, client):
        """
        CONTRACT: readiness endpoint lives at /api/v1/health/deep.
        If this path changes, CI gate configs must be updated in the same commit.
        """
        with patch("app.routes.health.functional_checks", return_value={
            "ok": True,
            "checks": {"db": {"ok": True, "latency_ms": 1, "detail": "connected"},
                       "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"}},
        }):
            resp = client.get(KNOWN_READINESS_PATH)
        assert resp.status_code == 200, (
            f"Readiness path has changed or is broken. "
            f"Known-good path is '{KNOWN_READINESS_PATH}'. "
            f"Got status {resp.status_code}."
        )

    def test_readiness_required_keys_characterization(self, client):
        """
        CONTRACT: readiness body must include: status, service, version,
        uptime_seconds, mock, checks. The 'mock' key is the canonical
        mock/live signal required by the Mock/Live Signal standard.
        The 'checks' dict enables per-dependency monitoring.
        """
        with patch("app.routes.health.functional_checks", return_value={
            "ok": True,
            "checks": {"db": {"ok": True, "latency_ms": 1, "detail": "connected"},
                       "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"}},
        }):
            resp = client.get(KNOWN_READINESS_PATH)
        data = resp.get_json()
        missing = KNOWN_READINESS_REQUIRED_KEYS - set(data.keys())
        assert not missing, (
            f"Readiness response is missing required keys: {missing}. "
            f"Known-good required keys: {KNOWN_READINESS_REQUIRED_KEYS}. "
            "The 'mock' key in particular is required for the Mock/Live Signal standard."
        )

    def test_readiness_503_when_critical_dep_down_characterization(self, client):
        """
        CONTRACT: readiness returns 503 when checks['ok'] is False.
        CI gates depend on this 503 to block deployments when deps are down.
        Changing this to always-200 would make CI gates silently pass on
        broken infrastructure.
        """
        with patch("app.routes.health.functional_checks", return_value={
            "ok": False,
            "checks": {"db": {"ok": False, "latency_ms": 10, "detail": "connection refused"},
                       "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"}},
        }):
            resp = client.get(KNOWN_READINESS_PATH)
        assert resp.status_code == 503, (
            f"Readiness must return 503 when any critical dependency is down. "
            f"Got {resp.status_code}. CI gates depend on this status code."
        )

    def test_mock_key_reflects_conductor_url_characterization(self, client):
        """
        CONTRACT: mock=True when CONDUCTOR_URL is empty/unset (mock mode).
        mock=False when CONDUCTOR_URL is set (live mode).
        This is the health-endpoint signal of the Mock/Live Signal standard.
        If this flips silently, operators can't tell if they're looking at
        real data or fixture data.
        """
        with patch.dict(os.environ, {"CONDUCTOR_URL": ""}):
            with patch("app.routes.health.functional_checks", return_value={
                "ok": True,
                "checks": {"db": {"ok": True, "latency_ms": 1, "detail": "connected"},
                           "conductor": {"ok": True, "latency_ms": None, "detail": "mock_mode"}},
            }):
                resp = client.get(KNOWN_READINESS_PATH)
        data = resp.get_json()
        assert data.get("mock") is True, (
            f"mock must be True when CONDUCTOR_URL is empty. "
            f"Got mock={data.get('mock')}. "
            "This is the Mock/Live Signal standard health-endpoint signal."
        )


class TestLegacyRedirectCharacterization:
    """Characterization: bare /health paths redirect 308 (transition shim)."""

    def test_bare_health_redirects_characterization(self, client):
        """
        CONTRACT: GET /health → 308 redirect to /api/v1/health.
        Bare /health is deprecated. This redirect stays until all monitoring
        configs are migrated, then the redirect is removed.
        """
        resp = client.get("/health")
        assert resp.status_code == 308, (
            f"GET /health must 308-redirect to /api/v1/health. "
            f"Got {resp.status_code}. "
            "Remove this redirect only after all monitoring configs are migrated."
        )
        assert "/api/v1/health" in resp.headers.get("Location", ""), (
            "Redirect must point to /api/v1/health."
        )

    def test_bare_health_deep_redirects_characterization(self, client):
        """
        CONTRACT: GET /health/deep → 308 redirect to /api/v1/health/deep.
        """
        resp = client.get("/health/deep")
        assert resp.status_code == 308, (
            f"GET /health/deep must 308-redirect to /api/v1/health/deep. "
            f"Got {resp.status_code}."
        )
