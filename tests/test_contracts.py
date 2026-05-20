"""Contract tests for all external integrations.

These tests document WHAT WE KNOW to be true about each integration — exact
URLs, exact header formats, exact field names, exact SOQL patterns, exact
webhook bodies. They are intentionally hardcoded.

Philosophy: a shape test (isinstance(result, dict)) lets you silently rename
a field and keep passing. A contract test fails the moment you change a URL,
a header format, an EEDM field name, or a SOQL column name that downstream
systems depend on. The hardcoded values ARE the specification.

When a TODO(vendor) is resolved and the real field name is confirmed, update
the contract test to assert the confirmed value and remove the TODO comment.
"""
import os
import smtplib
from unittest.mock import MagicMock, call, patch

import pytest
import requests as req_lib


# =============================================================================
# Ethos Provider — API contract tests
# =============================================================================

class TestEthosApiContracts:
    """Contract: Ethos EEDM REST API call shapes.

    Each test asserts the exact HTTP call the live path MUST make.
    If get_person() changes its URL pattern, the test breaks — intentionally.
    """

    def test_get_person_url_exact(self, monkeypatch):
        """CONTRACT: GET /api/persons/{guid} — exact URL, no trailing slash."""
        monkeypatch.setenv("ETHOS_URL", "https://integrate.elluciancloud.com")
        monkeypatch.setenv("ETHOS_API_KEY", "test-bearer-token")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp) as mock_get:
            ethos_provider.get_person("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
            url_called = mock_get.call_args[0][0]

        assert url_called == (
            "https://integrate.elluciancloud.com"
            "/api/persons/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        ), f"Expected exact Ethos persons URL, got: {url_called}"

    def test_get_person_auth_header_is_bearer(self, monkeypatch):
        """CONTRACT: Auth MUST be 'Bearer {api_key}' — not Basic, not X-Authorization."""
        monkeypatch.setenv("ETHOS_URL", "https://integrate.elluciancloud.com")
        monkeypatch.setenv("ETHOS_API_KEY", "my-secret-api-key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp) as mock_get:
            ethos_provider.get_person("some-guid")
            headers = mock_get.call_args[1]["headers"]

        assert headers["Authorization"] == "Bearer my-secret-api-key", (
            "Ethos auth must use Bearer token, not Basic or X-Authorization"
        )
        assert "Accept" in headers
        assert headers["Accept"] == "application/json"

    def test_get_person_timeout_is_10s(self, monkeypatch):
        """CONTRACT: All Ethos GET requests must use a 10s timeout."""
        monkeypatch.setenv("ETHOS_URL", "https://integrate.elluciancloud.com")
        monkeypatch.setenv("ETHOS_API_KEY", "key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp) as mock_get:
            ethos_provider.get_person("guid")
            timeout = mock_get.call_args[1]["timeout"]

        assert timeout == 10, f"Expected 10s timeout, got {timeout}"

    def test_search_persons_url_and_params(self, monkeypatch):
        """CONTRACT: Person search hits /api/persons with criteria + limit params."""
        monkeypatch.setenv("ETHOS_URL", "https://integrate.elluciancloud.com")
        monkeypatch.setenv("ETHOS_API_KEY", "key")
        from app import ethos_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        with patch("app.ethos_provider.requests.get", return_value=mock_resp) as mock_get:
            ethos_provider.search_persons("Smith", limit=10)
            url_called = mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]

        assert url_called == "https://integrate.elluciancloud.com/api/persons"
        assert params["criteria"] == "Smith", "Search query must go in 'criteria' param"
        assert params["limit"] == 10


class TestEthosEedmFieldContracts:
    """CONTRACT: Ethos EEDM persons v16 field names.

    These are the field paths our code reads from Ethos responses.
    If the EEDM spec uses different names, update here AND in the provider.
    Tests use the mock data, which must match the real API shape.
    """

    def setup_method(self):
        os.environ.pop("ETHOS_URL", None)
        os.environ.pop("ETHOS_API_KEY", None)

    def _get_mock_person(self, guid="test-guid-abc"):
        from app import ethos_provider
        return ethos_provider.get_person(guid)

    def test_eedm_top_level_id_field(self):
        """CONTRACT: EEDM persons resource top-level GUID is at .id"""
        p = self._get_mock_person("my-test-guid")
        assert p["id"] == "my-test-guid", \
            "EEDM persons: GUID must be at top-level 'id' field"

    def test_eedm_resource_field_value(self):
        """CONTRACT: resource field must be exactly 'persons' (lowercase plural)."""
        p = self._get_mock_person()
        assert p["resource"] == "persons", \
            "EEDM change notification: resource field must be 'persons'"

    def test_eedm_credentials_path(self):
        """CONTRACT: SIS_ID lives at .content.credentials[].type.credentialType"""
        p = self._get_mock_person()
        credentials = p["content"]["credentials"]
        assert isinstance(credentials, list), "credentials must be a list"
        assert len(credentials) > 0, "At least one credential expected"
        first = credentials[0]
        # These field names are from EEDM spec — do not rename without updating here
        assert "type" in first, "Each credential must have a 'type' object"
        assert "credentialType" in first["type"], \
            "Credential type discriminator must be at .type.credentialType"

    def test_eedm_sis_id_credential_type_value(self):
        """CONTRACT: Colleague person ID credential type is 'colleaguePersonId'."""
        p = self._get_mock_person()
        cred_types = [c["type"]["credentialType"] for c in p["content"]["credentials"]]
        assert "colleaguePersonId" in cred_types, (
            "EEDM spec: Colleague person ID must use credentialType 'colleaguePersonId'. "
            "If Ellucian changes this enum value, update sf_provider SOQL and JQ expressions."
        )

    def test_eedm_names_path(self):
        """CONTRACT: Person names at .content.names[] with firstName/lastName."""
        p = self._get_mock_person()
        names = p["content"]["names"]
        assert isinstance(names, list) and len(names) > 0
        assert "firstName" in names[0], "EEDM: name first component is 'firstName'"
        assert "lastName" in names[0], "EEDM: name last component is 'lastName'"

    def test_eedm_emails_path(self):
        """CONTRACT: Emails at .content.emails[].address with preference field."""
        p = self._get_mock_person()
        emails = p["content"]["emails"]
        assert isinstance(emails, list) and len(emails) > 0
        assert "address" in emails[0], "EEDM: email address field is 'address'"
        assert "preference" in emails[0], "EEDM: email preference field is 'preference'"

    def test_eedm_primary_email_preference_value(self):
        """CONTRACT: Primary email has preference == 'primary' (exact string)."""
        p = self._get_mock_person()
        primary = [e for e in p["content"]["emails"] if e.get("preference") == "primary"]
        assert len(primary) > 0, (
            "EEDM: primary email must have preference='primary'. "
            "JQ expression '.content.emails[] | select(.preference == \"primary\")' depends on this."
        )


# =============================================================================
# Salesforce Provider — API and field name contracts
# =============================================================================

class TestSalesforceApiContracts:
    """CONTRACT: Salesforce REST API call shapes and SOQL patterns."""

    def _sf_env(self, monkeypatch):
        import time
        monkeypatch.setenv("SF_USERNAME", "svc@doane.edu")
        monkeypatch.setenv("SF_PASSWORD", "pass")
        monkeypatch.setenv("SF_SECURITY_TOKEN", "tok")
        monkeypatch.setenv("SF_INSTANCE_URL", "https://doane.my.salesforce.com")
        from app import sf_provider
        sf_provider._token_cache.update({
            "token": "test-access-token",
            "instance_url": "https://doane.my.salesforce.com",
            "expires_at": time.time() + 3000,
        })

    def test_soql_query_url_uses_v59(self, monkeypatch):
        """CONTRACT: SOQL queries hit /services/data/v59.0/query"""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"records": [], "totalSize": 0, "done": True}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.find_person_by_sis_id("STU12345")
            url_called = mock_get.call_args[0][0]

        assert "/services/data/v59.0/query" in url_called, (
            f"SF SOQL must use /services/data/v59.0/query, got: {url_called}"
        )

    def test_soql_sis_id_field_name(self, monkeypatch):
        """CONTRACT: SIS_ID external ID field is 'SIS_ID__c' on Account."""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"records": [], "totalSize": 0, "done": True}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.find_person_by_sis_id("STU12345")
            params = mock_get.call_args[1]["params"]
            soql = params["q"]

        assert "SIS_ID__c" in soql, (
            f"SOQL must filter on SIS_ID__c, got: {soql}. "
            "If SF field is renamed, update Conductor workflows and upsert tasks too."
        )
        assert "STU12345" in soql
        assert "IsPersonAccount" in soql, "Must scope query to PersonAccount records only"

    def test_soql_ethos_guid_field_name(self, monkeypatch):
        """CONTRACT: Ethos GUID field is 'Ethos_Guid__c' on Account."""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"records": [], "totalSize": 0, "done": True}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.find_person_by_guid("abc-guid-123")
            params = mock_get.call_args[1]["params"]
            soql = params["q"]

        assert "Ethos_Guid__c" in soql, (
            f"SOQL must filter on Ethos_Guid__c, got: {soql}. "
            "Doane standard: Ethos GUID stored at Ethos_Guid__c (not d45, not legacy field)."
        )
        assert "abc-guid-123" in soql

    def test_soql_selects_required_account_fields(self, monkeypatch):
        """CONTRACT: Person lookup MUST SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c."""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"records": [], "totalSize": 0, "done": True}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.find_person_by_sis_id("STU99")
            soql = mock_get.call_args[1]["params"]["q"]

        required_fields = ["Id", "FirstName", "LastName", "SIS_ID__c", "Ethos_Guid__c"]
        for field in required_fields:
            assert field in soql, (
                f"SOQL must SELECT {field}. "
                "Removing this breaks the Correlation Tracer record display."
            )

    def test_auth_header_uses_bearer(self, monkeypatch):
        """CONTRACT: SF REST API auth header is 'Bearer {access_token}'."""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"records": [], "totalSize": 0, "done": True}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.find_person_by_sis_id("STU1")
            headers = mock_get.call_args[1]["headers"]

        assert headers["Authorization"] == "Bearer test-access-token", (
            "SF REST API requires 'Bearer {token}' auth. "
            "Doane standard: OAuth + service principal, not PAT."
        )

    def test_get_account_url_uses_sobjects(self, monkeypatch):
        """CONTRACT: Single-record fetch uses /sobjects/Account/{id}"""
        self._sf_env(monkeypatch)
        from app import sf_provider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Id": "001abc", "SIS_ID__c": "STU1"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.sf_provider.requests.get", return_value=mock_resp) as mock_get:
            sf_provider.get_account("001abc123")
            url_called = mock_get.call_args[0][0]

        assert "/sobjects/Account/001abc123" in url_called, (
            f"Account fetch must use /sobjects/Account/{{id}}, got: {url_called}"
        )


class TestSalesforceMockFieldContracts:
    """CONTRACT: SF mock data must match real Account schema.

    When confirmed field names are filled in (TODO resolved), these tests
    ensure the mock stays in sync with the live schema.
    """

    def setup_method(self):
        for k in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_INSTANCE_URL"):
            os.environ.pop(k, None)

    def test_mock_sis_id_field_name(self):
        """CONTRACT: SIS_ID stored at 'SIS_ID__c' in mock and real records."""
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU12345")
        record = result["records"][0]
        assert "SIS_ID__c" in record, (
            "Mock record must use 'SIS_ID__c' — same field name as live SF. "
            "If this field is renamed on the SF object, update Conductor upsert tasks."
        )
        assert record["SIS_ID__c"] == "STU12345"

    def test_mock_ethos_guid_field_name(self):
        """CONTRACT: Ethos GUID stored at 'Ethos_Guid__c' (not legacy d45 field)."""
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU12345")
        record = result["records"][0]
        assert "Ethos_Guid__c" in record, (
            "Mock record must use 'Ethos_Guid__c'. "
            "Doane standard: d45 keymaps are fully retired."
        )
        # Confirm legacy field is NOT present
        assert "d45" not in str(record).lower(), \
            "d45 legacy field must not appear in any SF record"

    def test_mock_result_shape_matches_sf_rest_response(self):
        """CONTRACT: Provider result wraps SF records in standard shape."""
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("STU1")
        # Our provider wraps the SF REST response
        assert "records" in result
        assert "record_count" in result
        assert "status" in result
        assert "diagnosis" in result
        assert result["record_count"] == len(result["records"])

    def test_mock_duplicate_detection_returns_two_records(self):
        """CONTRACT: duplicate SIS_ID must return exactly 2+ records, status='warning'."""
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("DUP12345")
        assert result["record_count"] >= 2, \
            "Duplicate detection: SIS_IDs containing 'dup' must return 2+ records"
        assert result["status"] == "warning"
        assert "DUPLICATE" in result["diagnosis"].upper()

    def test_mock_not_found_returns_zero_records(self):
        """CONTRACT: notfound identifier returns empty records, status='error'."""
        from app import sf_provider
        result = sf_provider.find_person_by_sis_id("NOTFOUND99")
        assert result["record_count"] == 0
        assert result["status"] == "error"
        assert "not found" in result["diagnosis"].lower()


# =============================================================================
# Notification Provider — delivery contract tests
# =============================================================================

class TestEmailDeliveryContracts:
    """CONTRACT: Email delivery must use STARTTLS on the configured SMTP host."""

    def _email_env(self, monkeypatch, to="ops@doane.edu"):
        monkeypatch.setenv("SMTP_HOST", "smtp.doane.edu")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "conductor@doane.edu")
        monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
        monkeypatch.setenv("DIGEST_EMAIL_FROM", "conductor-companion@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", to)

    def test_smtp_connects_to_configured_host_and_port(self, monkeypatch):
        """CONTRACT: SMTP must connect to SMTP_HOST:SMTP_PORT (not hardcoded)."""
        self._email_env(monkeypatch)
        from app import notification_provider

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", return_value=mock_smtp) as mock_cls:
            notification_provider.send_email("Test Subject", "<p>body</p>")
            mock_cls.assert_called_once_with("smtp.doane.edu", 587, timeout=15)

    def test_smtp_uses_starttls(self, monkeypatch):
        """CONTRACT: SMTP must call starttls() — plain text email is not acceptable."""
        self._email_env(monkeypatch)
        from app import notification_provider

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", return_value=mock_smtp):
            notification_provider.send_email("Subject", "<p>body</p>")
            mock_smtp.starttls.assert_called_once(), \
                "STARTTLS must be called — plain SMTP is not acceptable for credential delivery"

    def test_smtp_logins_with_configured_credentials(self, monkeypatch):
        """CONTRACT: SMTP login uses SMTP_USER + SMTP_PASSWORD."""
        self._email_env(monkeypatch)
        from app import notification_provider

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", return_value=mock_smtp):
            notification_provider.send_email("Subject", "<p>body</p>")
            mock_smtp.login.assert_called_once_with("conductor@doane.edu", "smtp-password")

    def test_smtp_sends_to_all_recipients(self, monkeypatch):
        """CONTRACT: All addresses in DIGEST_EMAIL_TO receive the email."""
        self._email_env(monkeypatch, to="ops@doane.edu,admin@doane.edu")
        from app import notification_provider

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", return_value=mock_smtp):
            notification_provider.send_email("Subject", "<p>body</p>")
            sendmail_call = mock_smtp.sendmail.call_args
            to_list = sendmail_call[0][1]

        assert "ops@doane.edu" in to_list
        assert "admin@doane.edu" in to_list

    def test_smtp_default_port_is_587(self, monkeypatch):
        """CONTRACT: Default SMTP port is 587 (STARTTLS), not 25 or 465."""
        self._email_env(monkeypatch)
        monkeypatch.delenv("SMTP_PORT", raising=False)
        from app import notification_provider

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", return_value=mock_smtp) as mock_cls:
            notification_provider.send_email("Subject", "<p>body</p>")
            _, port, *_ = mock_cls.call_args[0]

        assert port == 587, f"Default SMTP port must be 587 (STARTTLS), got {port}"

    def test_smtp_failure_returns_error_dict_not_raise(self, monkeypatch):
        """CONTRACT: SMTP failure returns {sent: False} — must never raise."""
        self._email_env(monkeypatch)
        from app import notification_provider

        with patch("app.notification_provider.smtplib.SMTP",
                   side_effect=smtplib.SMTPException("connection refused")):
            result = notification_provider.send_email("Subject", "<p>body</p>")

        assert result["sent"] is False
        assert result["error"] is not None


class TestGChatDeliveryContracts:
    """CONTRACT: GChat webhook delivery must POST exactly {"text": message}."""

    def test_gchat_posts_to_webhook_url(self, monkeypatch):
        """CONTRACT: GChat delivery POSTs to GCHAT_WEBHOOK_URL exactly."""
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/ABC/messages?key=xyz")
        from app import notification_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("app.notification_provider.requests.post", return_value=mock_resp) as mock_post:
            notification_provider.send_gchat("Test message")
            url_called = mock_post.call_args[0][0]

        assert url_called == "https://chat.googleapis.com/v1/spaces/ABC/messages?key=xyz"

    def test_gchat_body_is_text_key(self, monkeypatch):
        """CONTRACT: GChat webhook body must be {"text": message} — not "content", not "message"."""
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/X/messages?key=k")
        from app import notification_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("app.notification_provider.requests.post", return_value=mock_resp) as mock_post:
            notification_provider.send_gchat("Hello ops team")
            body = mock_post.call_args[1]["json"]

        assert body == {"text": "Hello ops team"}, (
            f"GChat webhook requires exactly {{\"text\": message}}, got: {body}"
        )

    def test_gchat_failure_returns_error_dict_not_raise(self, monkeypatch):
        """CONTRACT: GChat failure returns {sent: False} — must never raise."""
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/X")
        from app import notification_provider

        with patch("app.notification_provider.requests.post",
                   side_effect=req_lib.ConnectionError("refused")):
            result = notification_provider.send_gchat("message")

        assert result["sent"] is False
        assert result["error"] is not None


class TestDigestEmailFormatContracts:
    """CONTRACT: The HTML digest email must contain required structural elements."""

    def _sample_digest(self):
        return {
            "date": "2026-05-18",
            "workflows": [
                {"name": "EDA_Person_Sync", "total": 3412, "failed": 41,
                 "failure_rate_pct": 1.2, "avg_ms": 1200, "trend": "stable"},
                {"name": "EDA_ContactPoint_Sync", "total": 2891, "failed": 90,
                 "failure_rate_pct": 3.1, "avg_ms": 2100, "trend": "up"},
            ],
            "regressions": [
                {"workflow": "EDA_ContactPoint_Sync", "today_ms": 2100,
                 "yesterday_ms": 900, "pct_change": 133}
            ],
            "top_failures": [],
            "worker_health": {"status": "ok"},
            "recommendations": [],
        }

    def test_email_html_contains_date(self):
        """CONTRACT: Email must show the digest date prominently."""
        from app import notification_provider
        html = notification_provider.format_email_html(self._sample_digest())
        assert "2026-05-18" in html, "Digest date must appear in email HTML"

    def test_email_html_contains_workflow_names(self):
        """CONTRACT: Each workflow in the digest must appear in the email."""
        from app import notification_provider
        html = notification_provider.format_email_html(self._sample_digest())
        assert "EDA_Person_Sync" in html
        assert "EDA_ContactPoint_Sync" in html

    def test_email_html_contains_doane_branding(self):
        """CONTRACT: Email must include Doane brand orange (#FF7900) or navy (#1F3864)."""
        from app import notification_provider
        html = notification_provider.format_email_html(self._sample_digest())
        has_brand = "#FF7900" in html or "#1F3864" in html
        assert has_brand, "Digest email must include Doane brand colors"

    def test_email_html_contains_regression_highlight(self):
        """CONTRACT: Regressions section must appear when regressions exist."""
        from app import notification_provider
        html = notification_provider.format_email_html(self._sample_digest())
        assert "EDA_ContactPoint_Sync" in html
        # Regression pct should appear
        assert "133" in html, "Regression percentage must be visible in email"

    def test_gchat_message_contains_date(self):
        """CONTRACT: GChat message must include the digest date."""
        from app import notification_provider
        msg = notification_provider.format_gchat_message(self._sample_digest())
        assert "2026-05-18" in msg

    def test_gchat_message_is_string(self):
        """CONTRACT: format_gchat_message must return a plain string, not a dict."""
        from app import notification_provider
        msg = notification_provider.format_gchat_message(self._sample_digest())
        assert isinstance(msg, str), \
            "GChat message must be str — send_gchat wraps it in {\"text\": ...}"


# =============================================================================
# Conductor Client — API endpoint contracts
# =============================================================================

class TestConductorClientApiContracts:
    """CONTRACT: ConductorClient must call exact Conductor REST endpoints.

    These tests document the API surface we depend on from Orkes Conductor.
    If an endpoint path changes in a Conductor upgrade, these break — intentionally.
    """

    def _live_client(self, monkeypatch):
        monkeypatch.setenv("CONDUCTOR_URL", "https://conductor.doane.edu")
        monkeypatch.setenv("CONDUCTOR_API_KEY", "conductor-api-key")
        from app.conductor_client import ConductorClient
        return ConductorClient()

    def test_search_endpoint_path(self, monkeypatch):
        """CONTRACT: Execution search hits /api/workflow/search"""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"totalHits": 0, "results": []}
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.get", return_value=mock_resp) as mock_get:
            client.search(workflow_type="EDA_Person_Sync")
            url = mock_get.call_args[0][0]

        assert url == "https://conductor.doane.edu/api/workflow/search", \
            f"Search must hit /api/workflow/search, got {url}"

    def test_get_execution_endpoint_path(self, monkeypatch):
        """CONTRACT: Single execution fetch hits /api/workflow/{id}"""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"workflowId": "abc", "tasks": []}
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.get", return_value=mock_resp) as mock_get:
            client.get_execution("my-workflow-id-123")
            url = mock_get.call_args[0][0]

        assert url == "https://conductor.doane.edu/api/workflow/my-workflow-id-123"

    def test_retry_endpoint_path(self, monkeypatch):
        """CONTRACT: Workflow retry hits POST /api/workflow/{id}/retry"""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.post", return_value=mock_resp) as mock_post:
            client.retry_workflow("wf-to-retry")
            url = mock_post.call_args[0][0]

        assert url == "https://conductor.doane.edu/api/workflow/wf-to-retry/retry"

    def test_list_workflow_definitions_endpoint(self, monkeypatch):
        """CONTRACT: Workflow definitions list hits /api/metadata/workflow"""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.get", return_value=mock_resp) as mock_get:
            client.list_workflow_definitions()
            url = mock_get.call_args[0][0]

        assert url == "https://conductor.doane.edu/api/metadata/workflow"

    def test_auth_header_is_x_authorization(self, monkeypatch):
        """CONTRACT: Conductor auth uses X-Authorization header (not Bearer)."""
        client = self._live_client(monkeypatch)
        headers = client.get_headers()
        assert "X-Authorization" in headers, \
            "Conductor uses X-Authorization, not Authorization: Bearer"
        assert headers["X-Authorization"] == "conductor-api-key"

    def test_search_sort_is_start_time_desc(self, monkeypatch):
        """CONTRACT: Search results must be sorted startTime:DESC."""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"totalHits": 0, "results": []}
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.get", return_value=mock_resp) as mock_get:
            client.search()
            params = mock_get.call_args[1]["params"]

        assert params.get("sort") == "startTime:DESC", \
            "Search must always sort by startTime:DESC for consistent pagination"

    def test_worker_queue_endpoint_path(self, monkeypatch):
        """CONTRACT: Worker queue data hits /api/tasks/queue/all/verbose"""
        client = self._live_client(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None

        with patch("app.conductor_client.requests.get", return_value=mock_resp) as mock_get:
            client.get_all_task_queues()
            url = mock_get.call_args[0][0]

        assert url == "https://conductor.doane.edu/api/tasks/queue/all/verbose"
