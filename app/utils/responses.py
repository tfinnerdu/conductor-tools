"""Shared HTTP response helpers.

Every non-2xx API response must use error_response() — never inline the dict.
The request_id is threaded from the per-request before_request middleware
(see app/__init__.py). Falls back to "unknown" when middleware is absent
(e.g. tests that don't go through the full request stack).
"""
from flask import g, jsonify, Response


def error_response(message: str, code: str, status: int = 400) -> tuple[Response, int]:
    """Return a standards-compliant error envelope.

    Shape: {"error": "...", "code": "MACHINE_CODE", "request_id": "uuid"}
    The code field is a machine-readable string, never a raw HTTP status number.
    """
    return jsonify({
        "error": message,
        "code": code,
        "request_id": g.get("request_id", "unknown"),
    }), status
