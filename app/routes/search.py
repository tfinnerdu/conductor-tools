"""Advanced search routes — /api/v1/search/*"""
import csv
import io
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, Response

from app.conductor_client import ConductorClient
from app.models.saved_search import SavedSearch
from app import db
from app.utils.responses import error_response

search_bp = Blueprint("search", __name__, url_prefix="/api/v1/search")


def _matches_filter(result: dict, filters: list) -> bool:
    """Apply client-side post-filters to a single workflow result.

    Each filter is a dict with keys: path, operator, value
    Supported operators: eq, neq, contains, not_contains, exists, not_exists
    Path supports dot notation into nested dicts.
    """
    for f in filters:
        path = f.get("path", "")
        operator = f.get("operator", "eq")
        expected = f.get("value", "")

        # Resolve dot-path
        parts = path.split(".")
        node = result
        found = True
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                found = False
                break

        actual = str(node) if found else None

        if operator == "eq":
            if not found or actual != str(expected):
                return False
        elif operator == "neq":
            if found and actual == str(expected):
                return False
        elif operator == "contains":
            if not found or str(expected).lower() not in actual.lower():
                return False
        elif operator == "not_contains":
            if found and str(expected).lower() in actual.lower():
                return False
        elif operator == "exists":
            if not found:
                return False
        elif operator == "not_exists":
            if found:
                return False

    return True


@search_bp.route("/advanced", methods=["POST"])
def advanced_search():
    """Run a workflow search with optional client-side input field filters."""
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query", "")
        free_text = body.get("freeText", "")
        status = body.get("status", "")
        workflow_type = body.get("workflowType", "")
        start = int(body.get("start", 0))
        size = int(body.get("size", 100))
        filters = body.get("filters", [])

        client = ConductorClient()
        result = client.search(
            query=query,
            free_text=free_text,
            status=status,
            workflow_type=workflow_type,
            start=start,
            size=size,
        )

        results = result.get("results", [])

        # Apply input-field post-filters
        if filters:
            results = [r for r in results if _matches_filter(r, filters)]

        # Status summary counts
        status_counts = {}
        for r in results:
            s = r.get("status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

        return jsonify(
            {
                "totalHits": result.get("totalHits", len(results)),
                "results": results,
                "statusCounts": status_counts,
                "appliedFilters": len(filters),
            }
        )
    except Exception as exc:
        current_app.logger.error("advanced_search error: %s", exc, exc_info=True)
        return error_response(str(exc), "SEARCH_ERROR", 500)


@search_bp.route("/saved", methods=["GET"])
def list_saved_searches():
    """List all saved searches."""
    try:
        searches = SavedSearch.query.order_by(SavedSearch.use_count.desc()).all()
        return jsonify([s.to_dict() for s in searches])
    except Exception as exc:
        current_app.logger.error("list_saved_searches error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)


@search_bp.route("/saved", methods=["POST"])
def create_saved_search():
    """Create a new saved search."""
    try:
        body = request.get_json(force=True) or {}
        name = body.get("name", "").strip()
        if not name:
            return error_response("name is required", "VALIDATION_ERROR")

        saved = SavedSearch(
            name=name,
            description=body.get("description", ""),
            search_config=body.get("searchConfig", {}),
            created_by=body.get("createdBy", "user"),
        )
        db.session.add(saved)
        db.session.commit()
        return jsonify(saved.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("create_saved_search error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)


@search_bp.route("/saved/<int:search_id>", methods=["DELETE"])
def delete_saved_search(search_id):
    """Delete a saved search by ID."""
    try:
        saved = db.session.get(SavedSearch, search_id)
        if not saved:
            return error_response("Not found", "NOT_FOUND", 404)
        db.session.delete(saved)
        db.session.commit()
        return jsonify({"deleted": True, "id": search_id})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("delete_saved_search error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)


@search_bp.route("/export", methods=["POST"])
def export_csv():
    """Export search results as CSV."""
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query", "")
        status = body.get("status", "")
        workflow_type = body.get("workflowType", "")
        filters = body.get("filters", [])

        client = ConductorClient()
        result = client.search(
            query=query,
            status=status,
            workflow_type=workflow_type,
            size=500,
        )
        results = result.get("results", [])
        if filters:
            results = [r for r in results if _matches_filter(r, filters)]

        output = io.StringIO()
        fieldnames = [
            "workflowId", "workflowType", "status", "correlationId",
            "startTime", "endTime", "version",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            # Convert ms timestamps to ISO strings
            for tf in ("startTime", "endTime"):
                val = row.get(tf)
                if isinstance(val, (int, float)) and val > 0:
                    row[tf] = datetime.utcfromtimestamp(val / 1000).isoformat() + "Z"
            writer.writerow(row)

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=workflow_search_results.csv"},
        )
    except Exception as exc:
        current_app.logger.error("export_csv error: %s", exc, exc_info=True)
        return error_response(str(exc), "EXPORT_ERROR", 500)
