"""Tests for ConductorClient."""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestBuildQuery:
    """Tests for ConductorClient._build_query."""

    def setup_method(self):
        os.environ["CONDUCTOR_URL"] = "http://conductor.test:8080"
        from app.conductor_client import ConductorClient
        self.client = ConductorClient()

    def teardown_method(self):
        os.environ.pop("CONDUCTOR_URL", None)

    def test_build_query_with_all_parts(self):
        result = self.client._build_query("correlationId='X'", "FAILED", "order_fulfillment")
        assert "correlationId='X'" in result
        assert "status='FAILED'" in result
        assert "workflowType='order_fulfillment'" in result
        assert result.count(" AND ") == 2

    def test_build_query_empty(self):
        result = self.client._build_query("", "", "")
        assert result == ""

    def test_build_query_only_status(self):
        result = self.client._build_query("", "COMPLETED", "")
        assert result == "status='COMPLETED'"

    def test_build_query_only_workflow_type(self):
        result = self.client._build_query("", "", "my_workflow")
        assert result == "workflowType='my_workflow'"

    def test_build_query_custom_and_status(self):
        result = self.client._build_query("correlationId='test'", "RUNNING", "")
        assert "correlationId='test'" in result
        assert "status='RUNNING'" in result
        assert "workflowType" not in result


class TestGetHeaders:
    """Tests for ConductorClient.get_headers."""

    def setup_method(self):
        os.environ["CONDUCTOR_URL"] = "http://conductor.test:8080"

    def teardown_method(self):
        os.environ.pop("CONDUCTOR_URL", None)
        os.environ.pop("CONDUCTOR_API_KEY", None)

    def test_get_headers_with_api_key(self):
        os.environ["CONDUCTOR_API_KEY"] = "my-super-secret-key"
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        headers = client.get_headers()
        assert headers["X-Authorization"] == "my-super-secret-key"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    def test_get_headers_without_api_key(self):
        os.environ.pop("CONDUCTOR_API_KEY", None)
        from app.conductor_client import ConductorClient
        client = ConductorClient()
        headers = client.get_headers()
        assert "X-Authorization" not in headers
        assert headers["Content-Type"] == "application/json"


class TestSearchCallsCorrectEndpoint:
    """Tests for ConductorClient.search — verifies it calls the right URL."""

    def test_search_calls_correct_endpoint(self):
        os.environ["CONDUCTOR_URL"] = "http://conductor.test:8080"
        os.environ.pop("CONDUCTOR_API_KEY", None)

        mock_response = MagicMock()
        mock_response.json.return_value = {"totalHits": 0, "results": []}
        mock_response.raise_for_status.return_value = None

        with patch("requests.get", return_value=mock_response) as mock_get:
            from importlib import reload
            import app.conductor_client as cc_module
            reload(cc_module)
            client = cc_module.ConductorClient()

            result = client.search(status="COMPLETED", workflow_type="order_fulfillment")

            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert "api/workflow/search" in call_url
            assert result["totalHits"] == 0

        os.environ.pop("CONDUCTOR_URL", None)

    def test_search_falls_back_to_mock_on_error(self):
        """When CONDUCTOR_URL is set but the request fails, mock data is returned."""
        os.environ["CONDUCTOR_URL"] = "http://unreachable.test:9999"

        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("unreachable")):
            from importlib import reload
            import app.conductor_client as cc_module
            reload(cc_module)
            client = cc_module.ConductorClient()
            result = client.search(status="FAILED")

        assert "totalHits" in result
        assert "results" in result
        os.environ.pop("CONDUCTOR_URL", None)
