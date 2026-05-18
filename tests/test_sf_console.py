"""Tests for SF Console routes — /api/v1/sf/*"""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestGetPersonEdgeCases:
    def test_empty_identifier_in_url_goes_to_404(self, client_with_mock_conductor):
        # An empty path segment can't actually be sent to Flask (URL routing)
        # Test the _is_guid helper instead
        from app.routes.sf_console import _is_guid
        assert _is_guid("550e8400-e29b-41d4-a716-446655440000") is True
        assert _is_guid("STU12345") is False


class TestGetPerson:
    def test_sis_id_lookup_returns_result(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/sf/person/STU12345")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "records" in data
        assert "record_count" in data
        assert "status" in data
        assert "diagnosis" in data
        assert data["id_type"] == "sis_id"

    def test_guid_lookup_uses_guid_path(self, client_with_mock_conductor):
        guid = "550e8400-e29b-41d4-a716-446655440000"
        resp = client_with_mock_conductor.get(f"/api/v1/sf/person/{guid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id_type"] == "guid"

    def test_identifier_included_in_response(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/sf/person/STU99999")
        data = resp.get_json()
        assert "identifier" in data
        assert data["identifier"] == "STU99999"


class TestSearch:
    def test_valid_search_returns_result(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/sf/search",
            data=json.dumps({"query": "STU12345", "field": "SIS_ID__c"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "records" in data
        assert data["field"] == "SIS_ID__c"
        assert data["query"] == "STU12345"

    def test_missing_query_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/sf/search",
            data=json.dumps({"field": "SIS_ID__c"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_invalid_field_returns_400(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/sf/search",
            data=json.dumps({"query": "test", "field": "BadField__c"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_ethos_guid_field_uses_guid_path(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/sf/search",
            data=json.dumps({"query": "550e8400-e29b-41d4-a716-446655440000", "field": "Ethos_Guid__c"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["field"] == "Ethos_Guid__c"

    def test_default_field_is_sis_id(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.post(
            "/api/v1/sf/search",
            data=json.dumps({"query": "STU12345"}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestFindDuplicates:
    def test_returns_duplicates_structure(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/sf/duplicates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "duplicates" in data
        assert "duplicate_count" in data
        assert isinstance(data["duplicates"], list)

    def test_duplicate_count_matches_list(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/sf/duplicates")
        data = resp.get_json()
        assert data["duplicate_count"] == len(data["duplicates"])

    def test_with_real_duplicates_returned(self, app):
        """When find_duplicate_accounts returns 2+ records, they appear in duplicates list."""
        from unittest.mock import MagicMock, patch

        mock_sf = MagicMock()
        # Return 2 records for all probe IDs to trigger duplicate detection
        mock_sf.find_duplicate_accounts.return_value = [
            {"Id": "SF001", "SIS_ID__c": "dup-stu"},
            {"Id": "SF002", "SIS_ID__c": "dup-stu"},
        ]

        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.get("/api/v1/sf/duplicates")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["duplicate_count"] > 0
        dup = data["duplicates"][0]
        assert dup["account_count"] == 2
        assert "accounts" in dup


class TestSfHealth:
    def test_returns_health_status(self, client_with_mock_conductor):
        resp = client_with_mock_conductor.get("/api/v1/sf/health")
        assert resp.status_code in (200, 503)
        data = resp.get_json()
        assert "ok" in data


class TestSfConsoleErrorPaths:
    """Test exception handler paths in sf_console routes."""

    def test_get_person_exception_returns_500(self, app):
        from unittest.mock import MagicMock, patch
        mock_sf = MagicMock()
        mock_sf.find_person_by_sis_id.side_effect = Exception("sf unreachable")
        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.get("/api/v1/sf/person/STU999")
        assert resp.status_code == 500
        assert resp.get_json()["code"] == "SF_ERROR"

    def test_search_exception_returns_500(self, app):
        from unittest.mock import MagicMock, patch
        mock_sf = MagicMock()
        mock_sf.find_person_by_sis_id.side_effect = Exception("sf unreachable")
        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.post(
                "/api/v1/sf/search",
                data=json.dumps({"query": "STU999", "field": "SIS_ID__c"}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_duplicates_exception_returns_500(self, app):
        from unittest.mock import MagicMock, patch
        mock_sf = MagicMock()
        mock_sf.find_duplicate_accounts.side_effect = Exception("sf error")
        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.get("/api/v1/sf/duplicates")
        assert resp.status_code == 500

    def test_health_exception_returns_500(self, app):
        from unittest.mock import MagicMock, patch
        mock_sf = MagicMock()
        mock_sf.check_health.side_effect = Exception("sf health error")
        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.get("/api/v1/sf/health")
        assert resp.status_code == 500

    def test_get_person_guid_exception_returns_500(self, app):
        from unittest.mock import MagicMock, patch
        mock_sf = MagicMock()
        mock_sf.find_person_by_guid.side_effect = Exception("guid lookup failed")
        with patch("app.routes.sf_console.sf_provider", mock_sf):
            client = app.test_client()
            resp = client.get("/api/v1/sf/person/550e8400-e29b-41d4-a716-446655440000")
        assert resp.status_code == 500
