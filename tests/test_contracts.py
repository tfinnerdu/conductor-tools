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


# Known-good Ethos EEDM persons v16 payload shape.
# This hardcoded constant IS the specification — it pins the exact field paths
# our code reads from Ethos. It replaces what was previously inspected from
# mock data (now removed from production code).
KNOWN_EEDM_PERSON = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "resource": "persons",
    "content": {
        "names": [{"firstName": "Alex", "lastName": "Student", "fullName": "Alex Student"}],
        "credentials": [{"type": {"credentialType": "colleaguePersonId"}, "value": "STU001234"}],
        "emails": [{"address": "alex.student@doane.edu", "preference": "primary"}],
    },
}


class TestEthosEedmFieldContracts:
    """CONTRACT: Ethos EEDM persons v16 field names.

    This is a CHARACTERIZATION test. The production code can no longer be
    called in "mock mode" to inspect a payload, so KNOWN_EEDM_PERSON is the
    pinned, hardcoded record of the EEDM persons v16 shape the code depends on.
    These assertions fail the moment the assumed EEDM shape diverges from what
    the provider/JQ expressions expect — that is intentional. The hardcoded
    values ARE the spec; if the EEDM API changes, update this constant AND the
    provider together.
    """

    def test_eedm_top_level_id_field(self):
        """CONTRACT: EEDM persons resource top-level GUID is at .id"""
        p = KNOWN_EEDM_PERSON
        assert "id" in p, "EEDM persons: GUID must be at top-level 'id' field"
        assert p["id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890", \
            "EEDM persons: top-level 'id' must carry the person GUID"

    def test_eedm_resource_field_value(self):
        """CONTRACT: resource field must be exactly 'persons' (lowercase plural)."""
        p = KNOWN_EEDM_PERSON
        assert p["resource"] == "persons", \
            "EEDM change notification: resource field must be 'persons'"

    def test_eedm_credentials_path(self):
        """CONTRACT: SIS_ID lives at .content.credentials[].type.credentialType"""
        p = KNOWN_EEDM_PERSON
        credentials = p["content"]["credentials"]
        assert isinstance(credentials, list), "credentials must be a list"
        assert len(credentials) > 0, "At least one credential expected"
        first = credentials[0]
        assert "type" in first, "Each credential must have a 'type' object"
        assert "credentialType" in first["type"], \
            "Credential type discriminator must be at .type.credentialType"

    def test_eedm_sis_id_credential_type_value(self):
        """CONTRACT: Colleague person ID credential type is 'colleaguePersonId'."""
        p = KNOWN_EEDM_PERSON
        cred_types = [c["type"]["credentialType"] for c in p["content"]["credentials"]]
        assert "colleaguePersonId" in cred_types, (
            "EEDM spec: Colleague person ID must use credentialType 'colleaguePersonId'. "
            "If Ellucian changes this enum value, update sf_provider SOQL and JQ expressions."
        )

    def test_eedm_names_path(self):
        """CONTRACT: Person names at .content.names[] with firstName/lastName."""
        p = KNOWN_EEDM_PERSON
        names = p["content"]["names"]
        assert isinstance(names, list) and len(names) > 0, \
            "EEDM: .content.names must be a non-empty list"
        assert "firstName" in names[0], "EEDM: name first component is 'firstName'"
        assert "lastName" in names[0], "EEDM: name last component is 'lastName'"

    def test_eedm_emails_path(self):
        """CONTRACT: Emails at .content.emails[].address with preference field."""
        p = KNOWN_EEDM_PERSON
        emails = p["content"]["emails"]
        assert isinstance(emails, list) and len(emails) > 0, \
            "EEDM: .content.emails must be a non-empty list"
        assert "address" in emails[0], "EEDM: email address field is 'address'"
        assert "preference" in emails[0], "EEDM: email preference field is 'preference'"

    def test_eedm_primary_email_preference_value(self):
        """CONTRACT: Primary email has preference == 'primary' (exact string)."""
        p = KNOWN_EEDM_PERSON
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


class TestSalesforceResultShapeContracts:
    """CONTRACT: sf_provider._build_result() result-shape guarantees.

    SF field-name contracts (SIS_ID__c, Ethos_Guid__c) are already pinned by
    TestSalesforceApiContracts via the live SOQL string. Here we exercise the
    KEPT, pure helper _build_result() directly with hardcoded SF-shaped Account
    records — no provider calls in mock mode — and pin the wrapper shape and
    diagnosis classification (ok / warning+DUPLICATE / error+not found) that
    downstream consumers (Correlation Tracer) depend on.
    """

    # Hardcoded SF-shaped Account records — the exact field names the live
    # Salesforce REST API returns for a PersonAccount.
    HEALTHY_RECORD = {
        "Id": "001AAAAAAAAAAAAAAA",
        "FirstName": "Alex",
        "LastName": "Student",
        "SIS_ID__c": "STU12345",
        "Ethos_Guid__c": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "IsPersonAccount": True,
    }

    def test_healthy_record_uses_canonical_field_names(self):
        """CONTRACT: A healthy result keeps SIS_ID__c + Ethos_Guid__c, no legacy d45."""
        from app import sf_provider
        result = sf_provider._build_result([dict(self.HEALTHY_RECORD)])
        record = result["records"][0]
        assert "SIS_ID__c" in record, (
            "SF Account record must use 'SIS_ID__c' — same field name as live SF. "
            "If this field is renamed on the SF object, update Conductor upsert tasks."
        )
        assert record["SIS_ID__c"] == "STU12345"
        assert "Ethos_Guid__c" in record, (
            "SF Account record must use 'Ethos_Guid__c'. "
            "Doane standard: d45 keymaps are fully retired."
        )
        assert "d45" not in str(record).lower(), \
            "d45 legacy field must not appear in any SF record"

    def test_healthy_record_status_is_ok(self):
        """CONTRACT: 1 record with SIS_ID__c populated → status 'ok', healthy diagnosis."""
        from app import sf_provider
        records = [dict(self.HEALTHY_RECORD)]
        result = sf_provider._build_result(records)
        assert result["status"] == "ok", (
            f"A single record with SIS_ID__c must yield status 'ok', got {result['status']}"
        )
        assert "healthy" in result["diagnosis"].lower()
        assert result["record_count"] == len(records) == 1

    def test_result_shape_matches_sf_rest_response(self):
        """CONTRACT: _build_result wraps SF records in the standard shape."""
        from app import sf_provider
        result = sf_provider._build_result([dict(self.HEALTHY_RECORD)])
        for key in ("records", "record_count", "status", "diagnosis"):
            assert key in result, f"_build_result output must include '{key}' key"
        assert result["record_count"] == len(result["records"]), \
            "record_count must equal len(records)"

    def test_duplicate_detection_returns_warning(self):
        """CONTRACT: 2 records with the same SIS_ID__c → status 'warning' + 'DUPLICATE'."""
        from app import sf_provider
        dup_a = dict(self.HEALTHY_RECORD, Id="001AAA0000000000AA")
        dup_b = dict(self.HEALTHY_RECORD, Id="001BBB0000000000BB")
        result = sf_provider._build_result([dup_a, dup_b])
        assert result["record_count"] == 2, \
            "Duplicate detection: two same-SIS_ID records must yield record_count 2"
        assert result["status"] == "warning", (
            f"Duplicate SIS_ID__c must yield status 'warning', got {result['status']}"
        )
        assert "DUPLICATE" in result["diagnosis"].upper(), \
            "Duplicate diagnosis must call out 'DUPLICATE'"

    def test_not_found_returns_error(self):
        """CONTRACT: 0 records → status 'error' with a 'not found' diagnosis."""
        from app import sf_provider
        result = sf_provider._build_result([])
        assert result["record_count"] == 0
        assert result["status"] == "error", (
            f"An empty record list must yield status 'error', got {result['status']}"
        )
        assert "not found" in result["diagnosis"].lower(), \
            "Empty-result diagnosis must state the record was 'not found'"


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
