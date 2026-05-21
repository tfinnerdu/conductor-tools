"""Salesforce Console routes — /api/v1/sf/*"""
import re

from flask import Blueprint, current_app, jsonify, request

from app import sf_provider
from app.utils.responses import error_response

sf_console_bp = Blueprint("sf_console", __name__, url_prefix="/api/v1/sf")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_guid(identifier: str) -> bool:
    return bool(_UUID_RE.match(identifier.strip()))


@sf_console_bp.get("/person/<identifier>")
def get_person(identifier: str):
    """Look up a Salesforce PersonAccount.

    Auto-detects identifier type:
      - UUID format (8-4-4-4-12 hex) → treated as Ethos GUID → find_person_by_guid
      - Anything else                 → treated as SIS_ID     → find_person_by_sis_id
    """
    try:
        identifier = identifier.strip()
        if not identifier:
            return error_response("identifier is required", "VALIDATION_ERROR")

        if _is_guid(identifier):
            result = sf_provider.find_person_by_guid(identifier)
            id_type = "guid"
        else:
            result = sf_provider.find_person_by_sis_id(identifier)
            id_type = "sis_id"

        current_app.logger.info(
            "sf_console get_person: identifier=%s id_type=%s records=%d",
            identifier, id_type, result.get("record_count", 0),
        )
        return jsonify({**result, "identifier": identifier, "id_type": id_type})
    except Exception as exc:
        current_app.logger.error("sf_console get_person error: %s", exc, exc_info=True)
        return error_response(str(exc), "SF_ERROR", 500)


@sf_console_bp.post("/search")
def search():
    """Search Salesforce by a field value.

    Body: {query, field: "SIS_ID__c" | "Ethos_Guid__c" | "Name"}
    """
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query", "").strip()
        field = body.get("field", "SIS_ID__c").strip()

        if not query:
            return error_response("query is required", "VALIDATION_ERROR")

        allowed_fields = ("SIS_ID__c", "Ethos_Guid__c", "Name")
        if field not in allowed_fields:
            return error_response(
                f"field must be one of: {', '.join(allowed_fields)}",
                "VALIDATION_ERROR",
            )

        if field == "Ethos_Guid__c":
            result = sf_provider.find_person_by_guid(query)
        else:
            result = sf_provider.find_person_by_sis_id(query)

        current_app.logger.info(
            "sf_console search: field=%s query=%s records=%d",
            field, query, result.get("record_count", 0),
        )
        return jsonify({**result, "query": query, "field": field})
    except Exception as exc:
        current_app.logger.error("sf_console search error: %s", exc, exc_info=True)
        return error_response(str(exc), "SF_ERROR", 500)


@sf_console_bp.get("/duplicates")
def find_duplicates():
    """Find SIS_ID__c values that have more than one Account record.

    Checks a set of known SIS IDs using find_duplicate_accounts and returns
    those with more than one match.  In production this should be replaced
    by an aggregate SOQL query.
    """
    try:
        # In mock mode, probe a handful of sentinel SIS IDs to demonstrate
        # duplicate detection.  The 'dup' sentinel is guaranteed to return
        # two records from the mock.
        probe_ids = [
            "dup-student-001",
            "dup-student-002",
            "STU00001",
            "STU00002",
        ]

        duplicates = []
        for sis_id in probe_ids:
            accounts = sf_provider.find_duplicate_accounts(sis_id)
            if len(accounts) > 1:
                duplicates.append({
                    "sis_id": sis_id,
                    "account_count": len(accounts),
                    "accounts": accounts,
                })

        current_app.logger.info("sf_console find_duplicates: found=%d", len(duplicates))
        return jsonify({
            "duplicates": duplicates,
            "duplicate_count": len(duplicates),
        })
    except Exception as exc:
        current_app.logger.error("sf_console find_duplicates error: %s", exc, exc_info=True)
        return error_response(str(exc), "SF_ERROR", 500)


@sf_console_bp.get("/health")
def health():
    """Lightweight Salesforce API probe — read-only."""
    try:
        result = sf_provider.check_health()
        status_code = 200 if result.get("ok") else 503
        return jsonify(result), status_code
    except Exception as exc:
        current_app.logger.error("sf_console health error: %s", exc, exc_info=True)
        return error_response(str(exc), "SF_ERROR", 500)
