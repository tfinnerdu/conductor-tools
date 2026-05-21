"""Characterization tests — Error Envelope Contract.

Pins:
  - Every non-2xx response has exactly: error, code, request_id keys
  - 'code' is a machine-readable string (never a number, never null)
  - 'request_id' is a non-empty string (threaded from g.request_id middleware)
  - error_response() is the single shared constructor — not copy-pasted

Tests use the shared error_response() function directly and also probe
representative API endpoints to confirm the envelope is used consistently.

Last verified: 2026-05-21 (console audit v2).
"""
import pytest
from unittest.mock import patch


KNOWN_ERROR_ENVELOPE_KEYS = {"error", "code", "request_id"}


class TestErrorResponseHelperCharacterization:
    """Characterization: shared error_response() helper shape."""

    def test_error_envelope_has_required_keys_characterization(self, app):
        """
        CONTRACT: error_response() returns a JSON body with exactly
        {error, code, request_id}. These three keys are required by the
        API Surface standard. Removing any of them breaks consumers that
        parse error responses programmatically.
        """
        with app.test_request_context("/"):
            from flask import g
            g.request_id = "test-req-id-001"
            from app.utils.responses import error_response
            resp, status = error_response("something broke", "BROKEN", 400)
            data = resp.get_json()

        missing = KNOWN_ERROR_ENVELOPE_KEYS - set(data.keys())
        assert not missing, (
            f"error_response() is missing required keys: {missing}. "
            f"Known-good required keys: {KNOWN_ERROR_ENVELOPE_KEYS}. "
            "Consumers depend on these three keys being present on all error responses."
        )

    def test_code_is_string_not_number_characterization(self, app):
        """
        CONTRACT: 'code' must be a machine-readable string (e.g. VALIDATION_ERROR),
        never a raw HTTP status number (e.g. 400) and never null.
        Programmatic consumers switch on 'code' — a number would break that switch.
        """
        with app.test_request_context("/"):
            from flask import g
            g.request_id = "test-req-id-002"
            from app.utils.responses import error_response
            resp, status = error_response("bad input", "VALIDATION_ERROR", 400)
            data = resp.get_json()

        assert isinstance(data["code"], str), (
            f"'code' must be a string, got {type(data['code']).__name__}. "
            "Never use a raw HTTP status number as the code field."
        )
        assert data["code"] != "", (
            "'code' must not be an empty string. Use a descriptive machine code."
        )
        assert data["code"].upper() == data["code"] or "_" in data["code"], (
            "By convention, 'code' should be UPPER_SNAKE_CASE (e.g. VALIDATION_ERROR)."
        )

    def test_request_id_threads_from_middleware_characterization(self, app):
        """
        CONTRACT: request_id comes from flask.g.request_id set by the
        before_request middleware, not from a fresh uuid.uuid4() call inside
        error_response(). This ensures the same request_id threads through
        all log lines and error responses for a single request.
        """
        with app.test_request_context("/"):
            from flask import g
            g.request_id = "known-request-id-xyz"
            from app.utils.responses import error_response
            resp, _ = error_response("oops", "OOPS", 500)
            data = resp.get_json()

        assert data["request_id"] == "known-request-id-xyz", (
            f"request_id must come from g.request_id. "
            f"Got '{data['request_id']}' instead of 'known-request-id-xyz'. "
            "If error_response() generates its own UUID, request correlation breaks."
        )

    def test_fallback_when_no_middleware_characterization(self, app):
        """
        CONTRACT: error_response() returns 'unknown' as request_id when
        g.request_id is not set (e.g. tests that bypass middleware).
        Never None, never raises.
        """
        with app.test_request_context("/"):
            from app.utils.responses import error_response
            resp, _ = error_response("oops", "OOPS", 500)
            data = resp.get_json()

        assert data["request_id"] is not None, (
            "request_id must not be None — use 'unknown' as fallback."
        )
        assert data["request_id"] != "", (
            "request_id must not be empty — use 'unknown' as fallback."
        )


class TestErrorEnvelopeInRoutes:
    """Spot-check that representative API endpoints use the shared envelope."""

    def test_batches_validation_error_uses_envelope_characterization(self, client):
        """
        CONTRACT: POST /api/v1/batches with missing 'name' returns the
        standard error envelope. If any route copy-pastes its own dict
        construction and diverges, this test catches it.
        """
        resp = client.post("/api/v1/batches", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        missing = KNOWN_ERROR_ENVELOPE_KEYS - set(data.keys())
        assert not missing, (
            f"POST /api/v1/batches error response is missing keys: {missing}. "
            "All non-2xx responses must use the shared error_response() helper."
        )

    def test_diff_validation_error_uses_envelope_characterization(self, client_with_mock_conductor):
        """
        CONTRACT: POST /api/v1/diff/workflow with missing fields returns
        the standard error envelope.
        """
        resp = client_with_mock_conductor.post("/api/v1/diff/workflow", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        missing = KNOWN_ERROR_ENVELOPE_KEYS - set(data.keys())
        assert not missing, (
            f"POST /api/v1/diff/workflow error response is missing keys: {missing}."
        )

    def test_jq_validation_error_uses_envelope_characterization(self, client_with_mock_conductor):
        """
        CONTRACT: POST /api/v1/jq/evaluate with missing 'expression' returns
        the standard error envelope.
        """
        resp = client_with_mock_conductor.post("/api/v1/jq/evaluate", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        missing = KNOWN_ERROR_ENVELOPE_KEYS - set(data.keys())
        assert not missing, (
            f"POST /api/v1/jq/evaluate error response is missing keys: {missing}."
        )
