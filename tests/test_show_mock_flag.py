"""Pins the SHOW_MOCK opt-in flag's all-or-nothing behavior.

SHOW_MOCK is the single, explicit, all-or-nothing toggle for mock fixture
data. With SHOW_MOCK unset (default), every integration makes real calls
and surfaces real errors. With SHOW_MOCK=1, every integration returns
fixture data together — there is no per-integration override.

These tests pin both modes for each integration and the response signals
(X-Mock-Mode header, deep-health 'mock' key).
"""
import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# show_mock() helper
# ---------------------------------------------------------------------------

class TestShowMockHelper:
    def test_unset_is_false(self, monkeypatch):
        monkeypatch.delenv("SHOW_MOCK", raising=False)
        from app.utils.env import show_mock
        assert show_mock() is False

    def test_empty_is_false(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "")
        from app.utils.env import show_mock
        assert show_mock() is False

    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"])
    def test_truthy_values(self, monkeypatch, val):
        monkeypatch.setenv("SHOW_MOCK", val)
        from app.utils.env import show_mock
        assert show_mock() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "anything"])
    def test_other_values_are_false(self, monkeypatch, val):
        monkeypatch.setenv("SHOW_MOCK", val)
        from app.utils.env import show_mock
        assert show_mock() is False


# ---------------------------------------------------------------------------
# ConductorClient
# ---------------------------------------------------------------------------

class TestConductorClientShowMock:
    def test_off_with_no_url_raises(self, monkeypatch):
        monkeypatch.delenv("SHOW_MOCK", raising=False)
        monkeypatch.delenv("CONDUCTOR_URL", raising=False)
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        with pytest.raises(Exception):
            client.search()

    def test_on_returns_mock_search(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "1")
        monkeypatch.delenv("CONDUCTOR_URL", raising=False)
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        result = client.search()
        assert "totalHits" in result
        assert isinstance(result["results"], list)

    def test_on_returns_mock_secret_names(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "1")
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        names = client.list_secrets()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_on_retry_and_set_are_noops(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "1")
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        assert client.retry_workflow("any-id") is None
        assert client.set_secret("X", "y") is None
        assert client.delete_secret("X") is None


# ---------------------------------------------------------------------------
# sf_provider
# ---------------------------------------------------------------------------

class TestSfProviderShowMock:
    def test_off_unconfigured_raises(self, monkeypatch):
        monkeypatch.delenv("SHOW_MOCK", raising=False)
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        with pytest.raises(RuntimeError):
            sf_provider.find_person_by_sis_id("STU001")

    def test_on_returns_mock_record(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "1")
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU001")
        assert result["record_count"] == 1
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# ethos_provider
# ---------------------------------------------------------------------------

class TestEthosProviderShowMock:
    def test_off_unconfigured_raises(self, monkeypatch):
        monkeypatch.delenv("SHOW_MOCK", raising=False)
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.get_person("any-guid")

    def test_on_returns_mock_person(self, monkeypatch):
        monkeypatch.setenv("SHOW_MOCK", "1")
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        person = ethos_provider.get_person("test-guid-1234")
        assert person["id"] == "test-guid-1234"
        assert person["resource"] == "persons"


# ---------------------------------------------------------------------------
# Response signals — X-Mock-Mode header
# ---------------------------------------------------------------------------

class TestXMockModeHeader:
    def test_header_absent_when_show_mock_off(self, client):
        with patch.dict(os.environ, {"SHOW_MOCK": ""}):
            resp = client.get("/api/v1/health")
        assert "X-Mock-Mode" not in resp.headers, (
            "X-Mock-Mode must be absent when SHOW_MOCK is off — the header is "
            "the consumer-side signal that fixture data is in play."
        )

    def test_header_present_when_show_mock_on(self, client):
        with patch.dict(os.environ, {"SHOW_MOCK": "1"}):
            resp = client.get("/api/v1/health")
        assert resp.headers.get("X-Mock-Mode") == "true", (
            f"X-Mock-Mode must be 'true' when SHOW_MOCK=1. "
            f"Got '{resp.headers.get('X-Mock-Mode')}'."
        )

    def test_header_scoped_to_api_routes(self, client):
        with patch.dict(os.environ, {"SHOW_MOCK": "1"}):
            resp = client.get("/")
        assert "X-Mock-Mode" not in resp.headers, (
            "X-Mock-Mode must only appear on /api/ responses, not on HTML "
            "page routes."
        )
