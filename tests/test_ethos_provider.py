"""Tests for app/ethos_provider.py"""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestConfigured:
    def test_false_when_no_env(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        assert ethos_provider._configured() is False

    def test_false_when_only_url(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        assert ethos_provider._configured() is False

    def test_false_when_only_key(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider
        assert ethos_provider._configured() is False

    def test_true_when_both_set(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider
        assert ethos_provider._configured() is True


class TestGetPersonNotConfigured:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.get_person("some-guid")

    def test_raises_when_only_url(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.get_person("abc-guid")

    def test_raises_when_only_key(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.get_person("any-guid")

    def test_raises_before_any_request(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with patch("app.ethos_provider.requests.get") as mock_get:
            with pytest.raises(RuntimeError):
                ethos_provider.get_person("test-guid")
            mock_get.assert_not_called()


class TestGetPersonLivePath:
    def test_live_success(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "live-guid", "content": {}}
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp) as mock_get:
            result = ethos_provider.get_person("live-guid")
            mock_get.assert_called_once()
            assert result["id"] == "live-guid"

    def test_live_failure_propagates(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        with patch("app.ethos_provider.requests.get", side_effect=Exception("connection refused")):
            with pytest.raises(Exception):
                ethos_provider.get_person("fallback-guid")

    def test_live_http_error_propagates(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider
        import requests as req_lib

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("404")

        with patch("app.ethos_provider.requests.get", return_value=mock_resp):
            with pytest.raises(req_lib.HTTPError):
                ethos_provider.get_person("http-error-guid")


class TestIngestEvent:
    def test_ingest_adds_to_buffer(self, monkeypatch):
        from app import ethos_provider
        # Clear the buffer
        ethos_provider._event_buffer.clear()

        event = {"resource": "persons", "id": "test-guid", "operation": "updated"}
        ethos_provider.ingest_event(event)

        assert len(ethos_provider._event_buffer) == 1
        stored = ethos_provider._event_buffer[-1]
        assert stored["resource"] == "persons"
        assert "received_at" in stored

    def test_ingest_sets_received_at(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()

        event = {"resource": "courses", "id": "course-001"}
        ethos_provider.ingest_event(event)

        stored = ethos_provider._event_buffer[-1]
        assert "received_at" in stored
        # Should be a valid ISO string
        assert "T" in stored["received_at"]

    def test_buffer_max_size(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()

        # Fill past max (500)
        for i in range(510):
            ethos_provider.ingest_event({"resource": "persons", "id": f"guid-{i}"})

        assert len(ethos_provider._event_buffer) == 500


class TestGetRecentEvents:
    def test_filters_by_resource(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()

        ethos_provider.ingest_event({"resource": "persons", "id": "p1"})
        ethos_provider.ingest_event({"resource": "courses", "id": "c1"})
        ethos_provider.ingest_event({"resource": "persons", "id": "p2"})

        persons_events = ethos_provider.get_recent_events(resource="persons")
        assert len(persons_events) == 2
        for e in persons_events:
            assert e["resource"] == "persons"

    def test_respects_limit(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()

        for i in range(10):
            ethos_provider.ingest_event({"resource": "persons", "id": f"guid-{i}"})

        events = ethos_provider.get_recent_events(resource="persons", limit=3)
        assert len(events) == 3

    def test_empty_when_no_matching_resource(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()

        ethos_provider.ingest_event({"resource": "persons", "id": "p1"})
        events = ethos_provider.get_recent_events(resource="courses")
        assert events == []

    def test_returns_list(self, monkeypatch):
        from app import ethos_provider
        ethos_provider._event_buffer.clear()
        events = ethos_provider.get_recent_events()
        assert isinstance(events, list)


class TestResolveIdentity:
    def test_passthrough_in_mock_mode(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        assert ethos_provider.resolve_identity("STU12345") == "STU12345"

    def test_passthrough_with_source_arg(self, monkeypatch):
        from app import ethos_provider
        assert ethos_provider.resolve_identity("some-guid", source="guid") == "some-guid"


class TestCheckHealth:
    def test_not_configured_returns_ok(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        result = ethos_provider.check_health()
        assert result["ok"] is True
        assert result["detail"] == "not_configured"
        assert result["latency_ms"] is None

    def test_reachable_returns_ok_true(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp):
            result = ethos_provider.check_health()
            assert result["ok"] is True
            assert result["detail"] == "reachable"
            assert isinstance(result["latency_ms"], int)

    def test_server_error_returns_ok_false(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp):
            result = ethos_provider.check_health()
            assert result["ok"] is False
            assert "http_500" in result["detail"]

    def test_timeout_returns_ok_false(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider
        import requests as req_lib

        with patch("app.ethos_provider.requests.get", side_effect=req_lib.Timeout("timeout")):
            result = ethos_provider.check_health()
            assert result["ok"] is False
            assert result["detail"] == "timeout"

    def test_generic_exception_returns_ok_false(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        with patch("app.ethos_provider.requests.get", side_effect=Exception("connection refused")):
            result = ethos_provider.check_health()
            assert result["ok"] is False
            assert "connection refused" in result["detail"]


class TestSearchPersons:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.search_persons("Alex")

    def test_raises_when_not_configured_with_limit(self, monkeypatch):
        monkeypatch.delenv("ETHOS_URL", raising=False)
        monkeypatch.delenv("ETHOS_API_KEY", raising=False)
        from app import ethos_provider
        with pytest.raises(RuntimeError):
            ethos_provider.search_persons("test", limit=2)

    def test_live_success(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "g1"}, {"id": "g2"}]
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp):
            results = ethos_provider.search_persons("Smith")
            assert len(results) == 2

    def test_live_failure_propagates(self, monkeypatch):
        monkeypatch.setenv("ETHOS_URL", "https://ethos.example.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-key")
        from app import ethos_provider

        with patch("app.ethos_provider.requests.get", side_effect=Exception("fail")):
            with pytest.raises(Exception):
                ethos_provider.search_persons("Smith")
