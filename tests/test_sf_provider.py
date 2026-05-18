"""Tests for app/sf_provider.py"""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestConfigured:
    def test_false_when_no_env(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        assert sf_provider._configured() is False

    def test_true_with_user_pass_token(self, monkeypatch):
        monkeypatch.setenv("SF_USERNAME", "user@doane.edu")
        monkeypatch.setenv("SF_PASSWORD", "pass")
        monkeypatch.setenv("SF_SECURITY_TOKEN", "token123")
        monkeypatch.delenv("SF_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("SF_INSTANCE_URL", raising=False)
        from app import sf_provider
        assert sf_provider._configured() is True

    def test_true_with_access_token_and_instance_url(self, monkeypatch):
        monkeypatch.delenv("SF_USERNAME", raising=False)
        monkeypatch.delenv("SF_PASSWORD", raising=False)
        monkeypatch.delenv("SF_SECURITY_TOKEN", raising=False)
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://myinstance.salesforce.com")
        from app import sf_provider
        assert sf_provider._configured() is True

    def test_false_with_only_access_token(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        from app import sf_provider
        assert sf_provider._configured() is False


class TestFindPersonBySisId:
    def test_mock_returns_records(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU12345")
        assert isinstance(result, dict)
        assert "records" in result
        assert "record_count" in result
        assert "status" in result
        assert "diagnosis" in result

    def test_mock_healthy_record(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU12345")
        assert result["status"] == "ok"
        assert result["record_count"] == 1
        assert "healthy" in result["diagnosis"].lower()

    def test_mock_dup_returns_two_records(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("dup-student")
        assert result["record_count"] == 2
        assert result["status"] == "warning"
        assert "DUPLICATE" in result["diagnosis"]

    def test_mock_notfound_returns_zero(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("notfound-student")
        assert result["record_count"] == 0
        assert result["status"] == "error"

    def test_mock_missing_sis_id_is_warning(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("missing-person")
        assert result["status"] == "warning"
        assert "missing" in result["diagnosis"].lower()


class TestFindPersonByGuid:
    def test_mock_returns_records(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_guid("550e8400-e29b-41d4-a716-446655440000")
        assert isinstance(result, dict)
        assert "records" in result
        assert result["record_count"] >= 1

    def test_mock_notfound_returns_empty(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_guid("notfound-guid-12345")
        assert result["record_count"] == 0
        assert result["status"] == "error"

    def test_mock_result_has_ethos_guid_field(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_person_by_guid("test-guid-12345")
        assert result["record_count"] == 1
        record = result["records"][0]
        assert "Ethos_Guid__c" in record


class TestFindDuplicateAccounts:
    def test_mock_returns_list(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_duplicate_accounts("STU12345")
        assert isinstance(result, list)

    def test_mock_dup_returns_two(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_duplicate_accounts("dup-student")
        assert len(result) == 2

    def test_mock_healthy_returns_one(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_duplicate_accounts("STU00001")
        assert len(result) == 1

    def test_mock_notfound_returns_empty(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.find_duplicate_accounts("notfound-x")
        assert result == []


class TestGetAccount:
    def test_mock_returns_dict(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.get_account("SF001AAA")
        assert isinstance(result, dict)
        assert result["Id"] == "SF001AAA"

    def test_mock_has_required_fields(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.get_account("SF001AAA")
        assert "FirstName" in result
        assert "LastName" in result
        assert "SIS_ID__c" in result
        assert "IsPersonAccount" in result


class TestCheckHealth:
    def test_not_configured_returns_ok(self, monkeypatch):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_ACCESS_TOKEN", "SF_INSTANCE_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import sf_provider
        result = sf_provider.check_health()
        assert result["ok"] is True
        assert result["detail"] == "not_configured"
        assert result["latency_ms"] is None

    def test_configured_reachable(self, monkeypatch):
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://myinstance.salesforce.com")
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("app.sf_provider.requests.get", return_value=mock_resp):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.check_health()
                assert result["ok"] is True
                assert result["detail"] == "reachable"

    def test_configured_timeout(self, monkeypatch):
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://myinstance.salesforce.com")
        from app import sf_provider
        import requests as req_lib

        with patch("app.sf_provider.requests.get", side_effect=req_lib.Timeout("timeout")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.check_health()
                assert result["ok"] is False
                assert result["detail"] == "timeout"

    def test_configured_generic_exception(self, monkeypatch):
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://myinstance.salesforce.com")
        from app import sf_provider

        with patch("app.sf_provider.requests.get", side_effect=Exception("connection refused")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.check_health()
                assert result["ok"] is False
                assert "connection refused" in result["detail"]


class TestSfProviderRealPaths:
    """Test real API paths with mocked requests."""

    def _setup_live_env(self, monkeypatch):
        monkeypatch.setenv("SF_ACCESS_TOKEN", "bearer-token")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://myinstance.salesforce.com")
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN"):
            monkeypatch.delenv(k, raising=False)

    def test_find_person_by_sis_id_live_success(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalSize": 1,
            "done": True,
            "records": [{"Id": "SF001", "SIS_ID__c": "STU001", "FirstName": "Alex", "LastName": "Student"}]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.find_person_by_sis_id("STU001")
                assert result["record_count"] == 1
                assert result["status"] == "ok"

    def test_find_person_by_sis_id_live_failure_fallback(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        with patch("app.sf_provider.requests.get", side_effect=Exception("network error")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.find_person_by_sis_id("STU001")
                # Falls back to mock
                assert isinstance(result, dict)
                assert "records" in result

    def test_find_person_by_guid_live_success(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        guid = "550e8400-e29b-41d4-a716-446655440000"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalSize": 1,
            "done": True,
            "records": [{"Id": "SF001", "Ethos_Guid__c": guid, "SIS_ID__c": "STU001"}]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.find_person_by_guid(guid)
                assert result["record_count"] == 1

    def test_find_person_by_guid_live_failure_fallback(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        with patch("app.sf_provider.requests.get", side_effect=Exception("fail")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.find_person_by_guid("some-guid")
                assert isinstance(result, dict)

    def test_find_duplicate_accounts_live_success(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalSize": 2,
            "done": True,
            "records": [
                {"Id": "SF001", "SIS_ID__c": "STU001"},
                {"Id": "SF002", "SIS_ID__c": "STU001"},
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                records = sf_provider.find_duplicate_accounts("STU001")
                assert len(records) == 2

    def test_find_duplicate_accounts_live_failure_fallback(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        with patch("app.sf_provider.requests.get", side_effect=Exception("fail")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                records = sf_provider.find_duplicate_accounts("STU001")
                assert isinstance(records, list)

    def test_get_account_live_success(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Id": "SF001AAA", "FirstName": "Alex"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.get_account("SF001AAA")
                assert result["Id"] == "SF001AAA"

    def test_get_account_live_failure_fallback(self, monkeypatch):
        self._setup_live_env(monkeypatch)
        from app import sf_provider

        with patch("app.sf_provider.requests.get", side_effect=Exception("fail")):
            with patch("app.sf_provider._get_access_token", return_value="bearer-token"):
                result = sf_provider.get_account("SF001AAA")
                assert isinstance(result, dict)

    def test_get_access_token_with_direct_token(self, monkeypatch):
        monkeypatch.setenv("SF_ACCESS_TOKEN", "direct-bearer-token")
        from app import sf_provider
        token = sf_provider._get_access_token()
        assert token == "direct-bearer-token"

    def test_get_access_token_via_oauth_flow(self, monkeypatch):
        """Tests the username/password OAuth flow."""
        monkeypatch.delenv("SF_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("SF_USERNAME", "user@doane.edu")
        monkeypatch.setenv("SF_PASSWORD", "pass")
        monkeypatch.setenv("SF_SECURITY_TOKEN", "tok")
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "oauth-token-123"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.post", return_value=mock_resp):
            token = sf_provider._get_access_token()
            assert token == "oauth-token-123"

    def test_build_result_zero_records(self):
        from app import sf_provider
        result = sf_provider._build_result([])
        assert result["status"] == "error"
        assert result["record_count"] == 0

    def test_build_result_duplicate_records(self):
        from app import sf_provider
        records = [
            {"Id": "SF001", "SIS_ID__c": "STU001"},
            {"Id": "SF002", "SIS_ID__c": "STU001"},
        ]
        result = sf_provider._build_result(records)
        assert result["status"] == "warning"
        assert "DUPLICATE" in result["diagnosis"]

    def test_build_result_missing_sis_id(self):
        from app import sf_provider
        records = [{"Id": "SF001", "SIS_ID__c": None}]
        result = sf_provider._build_result(records)
        assert result["status"] == "warning"
        assert "missing" in result["diagnosis"].lower()
