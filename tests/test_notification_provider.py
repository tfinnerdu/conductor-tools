"""Tests for app/notification_provider.py"""
import os
from unittest.mock import MagicMock, patch

import pytest


SAMPLE_DIGEST = {
    "date": "2026-01-15",
    "generated_at": "2026-01-15T06:00:00+00:00",
    "workflows": [
        {"name": "student_enrollment", "total": 100, "failed": 5, "avg_ms": 1500, "trend": "up",
         "failure_rate_pct": 5.0},
        {"name": "order_fulfillment", "total": 50, "failed": 0, "avg_ms": 800, "trend": "stable",
         "failure_rate_pct": 0.0},
    ],
    "regressions": [
        {
            "workflow_name": "student_enrollment",
            "current_avg_ms": 1500,
            "historical_avg_ms": 900,
            "pct_slower": 66.7,
        }
    ],
    "top_failures": [],
    "worker_health": {
        "enroll_student": "healthy",
        "process_payment": "down",
    },
}


class TestEmailConfigured:
    def test_false_when_env_missing(self, monkeypatch):
        for k in ("SMTP_HOST", "SMTP_USER", "DIGEST_EMAIL_TO"):
            monkeypatch.delenv(k, raising=False)
        from app import notification_provider
        assert notification_provider._email_configured() is False

    def test_false_when_only_smtp_host(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("DIGEST_EMAIL_TO", raising=False)
        from app import notification_provider
        assert notification_provider._email_configured() is False

    def test_true_when_all_set(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "conductor@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "admin@doane.edu")
        from app import notification_provider
        assert notification_provider._email_configured() is True


class TestGchatConfigured:
    def test_false_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
        from app import notification_provider
        assert notification_provider._gchat_configured() is False

    def test_true_when_set(self, monkeypatch):
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider
        assert notification_provider._gchat_configured() is True


class TestFormatEmailHtml:
    def test_contains_date(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "2026-01-15" in html

    def test_contains_workflow_table(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "student_enrollment" in html
        assert "order_fulfillment" in html

    def test_contains_doane_brand_colors(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "#FF7900" in html
        assert "#1F3864" in html

    def test_contains_regression_section(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "Regression" in html or "regression" in html.lower()

    def test_contains_worker_health(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "enroll_student" in html
        assert "process_payment" in html

    def test_contains_footer_link(self):
        from app import notification_provider
        html = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert "Conductor Companion" in html

    def test_returns_string(self):
        from app import notification_provider
        result = notification_provider.format_email_html(SAMPLE_DIGEST)
        assert isinstance(result, str)

    def test_empty_digest_doesnt_crash(self):
        from app import notification_provider
        html = notification_provider.format_email_html({})
        assert isinstance(html, str)


class TestFormatGchatMessage:
    def test_contains_date(self):
        from app import notification_provider
        msg = notification_provider.format_gchat_message(SAMPLE_DIGEST)
        assert "2026-01-15" in msg

    def test_contains_workflow_names(self):
        from app import notification_provider
        msg = notification_provider.format_gchat_message(SAMPLE_DIGEST)
        assert "student_enrollment" in msg

    def test_contains_regression_info(self):
        from app import notification_provider
        msg = notification_provider.format_gchat_message(SAMPLE_DIGEST)
        assert "Regression" in msg or "regression" in msg.lower() or "66.7" in msg

    def test_contains_worker_issue(self):
        from app import notification_provider
        msg = notification_provider.format_gchat_message(SAMPLE_DIGEST)
        # process_payment is "down"
        assert "process_payment" in msg

    def test_returns_string(self):
        from app import notification_provider
        result = notification_provider.format_gchat_message(SAMPLE_DIGEST)
        assert isinstance(result, str)

    def test_empty_digest_doesnt_crash(self):
        from app import notification_provider
        msg = notification_provider.format_gchat_message({})
        assert isinstance(msg, str)


class TestSendEmail:
    def test_not_configured_returns_error(self, monkeypatch):
        for k in ("SMTP_HOST", "SMTP_USER", "DIGEST_EMAIL_TO"):
            monkeypatch.delenv(k, raising=False)
        from app import notification_provider
        result = notification_provider.send_email("Test Subject", "<p>Hello</p>")
        assert result["sent"] is False
        assert result["error"] == "email not configured"

    def test_smtp_failure_returns_error(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "conductor@doane.edu")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "admin@doane.edu")
        from app import notification_provider
        import smtplib

        with patch("app.notification_provider.smtplib.SMTP", side_effect=smtplib.SMTPException("connection refused")):
            result = notification_provider.send_email("Test", "<p>body</p>")
            assert result["sent"] is False
            assert result["error"] is not None
            assert len(result["error"]) > 0

    def test_smtp_success(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "conductor@doane.edu")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("DIGEST_EMAIL_FROM", "conductor@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "admin@doane.edu")
        from app import notification_provider

        mock_smtp_instance = MagicMock()
        mock_smtp_class = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.notification_provider.smtplib.SMTP", mock_smtp_class):
            result = notification_provider.send_email("Test", "<p>body</p>")
            assert result["sent"] is True
            assert result["error"] is None


class TestSendGchat:
    def test_not_configured_returns_error(self, monkeypatch):
        monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
        from app import notification_provider
        result = notification_provider.send_gchat("Test message")
        assert result["sent"] is False
        assert result["error"] == "gchat not configured"

    def test_success(self, monkeypatch):
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("app.notification_provider.requests.post", return_value=mock_resp):
            result = notification_provider.send_gchat("Hello GChat")
            assert result["sent"] is True
            assert result["error"] is None

    def test_request_failure_returns_error(self, monkeypatch):
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider

        with patch("app.notification_provider.requests.post", side_effect=Exception("network error")):
            result = notification_provider.send_gchat("Hello GChat")
            assert result["sent"] is False
            assert result["error"] is not None


class TestDeliverDigest:
    def test_no_channels_configured(self, monkeypatch):
        for k in ("SMTP_HOST", "SMTP_USER", "DIGEST_EMAIL_TO", "GCHAT_WEBHOOK_URL"):
            monkeypatch.delenv(k, raising=False)
        from app import notification_provider
        result = notification_provider.deliver_digest(SAMPLE_DIGEST)
        assert result["channels_attempted"] == 0
        assert result["channels_succeeded"] == 0
        assert result["errors"] == []

    def test_gchat_channel_success(self, monkeypatch):
        for k in ("SMTP_HOST", "SMTP_USER", "DIGEST_EMAIL_TO"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider

        with patch("app.notification_provider.send_gchat", return_value={"sent": True, "error": None}):
            result = notification_provider.deliver_digest(SAMPLE_DIGEST)
            assert result["channels_attempted"] == 1
            assert result["channels_succeeded"] == 1

    def test_email_channel_success(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "u@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "a@doane.edu")
        monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
        from app import notification_provider

        with patch("app.notification_provider.send_email", return_value={"sent": True, "error": None}):
            result = notification_provider.deliver_digest(SAMPLE_DIGEST)
            assert result["channels_attempted"] == 1
            assert result["channels_succeeded"] == 1

    def test_channel_failure_recorded_in_errors(self, monkeypatch):
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        for k in ("SMTP_HOST", "SMTP_USER", "DIGEST_EMAIL_TO"):
            monkeypatch.delenv(k, raising=False)
        from app import notification_provider

        with patch("app.notification_provider.send_gchat", return_value={"sent": False, "error": "network error"}):
            result = notification_provider.deliver_digest(SAMPLE_DIGEST)
            assert result["channels_attempted"] == 1
            assert result["channels_succeeded"] == 0
            assert len(result["errors"]) == 1

    def test_never_raises_when_both_channels_throw(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "u@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "a@doane.edu")
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider

        with patch("app.notification_provider.send_email", side_effect=Exception("email boom")):
            with patch("app.notification_provider.send_gchat", side_effect=Exception("gchat boom")):
                # Must not raise
                result = notification_provider.deliver_digest(SAMPLE_DIGEST)
                assert isinstance(result, dict)
                assert "channels_attempted" in result

    def test_email_channel_failure_recorded(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "u@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "a@doane.edu")
        monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
        from app import notification_provider

        with patch("app.notification_provider.send_email", return_value={"sent": False, "error": "auth failed"}):
            result = notification_provider.deliver_digest(SAMPLE_DIGEST)
            assert result["channels_attempted"] == 1
            assert result["channels_succeeded"] == 0
            assert len(result["errors"]) == 1
            assert result["errors"][0]["channel"] == "email"

    def test_both_channels_attempted(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "u@doane.edu")
        monkeypatch.setenv("DIGEST_EMAIL_TO", "a@doane.edu")
        monkeypatch.setenv("GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/xxx/messages?key=yyy")
        from app import notification_provider

        with patch("app.notification_provider.send_email", return_value={"sent": True, "error": None}):
            with patch("app.notification_provider.send_gchat", return_value={"sent": True, "error": None}):
                result = notification_provider.deliver_digest(SAMPLE_DIGEST)
                assert result["channels_attempted"] == 2
                assert result["channels_succeeded"] == 2
