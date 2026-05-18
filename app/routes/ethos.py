"""Ethos Integration routes — /api/v1/ethos/*"""
import uuid

from flask import Blueprint, current_app, jsonify, request

from app import ethos_provider

ethos_bp = Blueprint("ethos", __name__, url_prefix="/api/v1/ethos")


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


@ethos_bp.get("/person/<guid>")
def get_person(guid: str):
    """Fetch a person record from Ethos by GUID."""
    try:
        person = ethos_provider.get_person(guid)
        return jsonify(person)
    except Exception as exc:
        current_app.logger.error("ethos get_person error: %s", exc, exc_info=True)
        return _error(str(exc), "ETHOS_ERROR", 500)


@ethos_bp.get("/events")
def get_events():
    """Return recent Ethos change events from the in-memory buffer.

    Query params:
      - resource (default: persons)
      - limit    (default: 50)
    """
    try:
        resource = request.args.get("resource", "persons")
        limit = int(request.args.get("limit", 50))
        events = ethos_provider.get_recent_events(resource=resource, limit=limit)
        return jsonify({"events": events, "count": len(events), "resource": resource})
    except Exception as exc:
        current_app.logger.error("ethos get_events error: %s", exc, exc_info=True)
        return _error(str(exc), "ETHOS_ERROR", 500)


@ethos_bp.post("/events")
def ingest_event():
    """Ingest an Ethos change notification event.

    Body: {resource, id, operation, content?, ...}
    """
    try:
        body = request.get_json(force=True) or {}
        if not body.get("resource"):
            return _error("resource is required", "VALIDATION_ERROR")

        from app import ethos_provider as ep
        ep.ingest_event(body)

        return jsonify({
            "received": True,
            "buffer_size": len(ep._event_buffer),
        })
    except Exception as exc:
        current_app.logger.error("ethos ingest_event error: %s", exc, exc_info=True)
        return _error(str(exc), "ETHOS_ERROR", 500)


@ethos_bp.get("/health")
def health():
    """Lightweight Ethos API probe — read-only."""
    try:
        result = ethos_provider.check_health()
        status_code = 200 if result.get("ok") else 503
        return jsonify(result), status_code
    except Exception as exc:
        current_app.logger.error("ethos health error: %s", exc, exc_info=True)
        return _error(str(exc), "ETHOS_ERROR", 500)


@ethos_bp.post("/search")
def search_persons():
    """Search Ethos for persons.

    Body: {query, limit}
    """
    try:
        body = request.get_json(force=True) or {}
        query = body.get("query", "").strip()
        limit = int(body.get("limit", 20))

        if not query:
            return _error("query is required", "VALIDATION_ERROR")

        results = ethos_provider.search_persons(query=query, limit=limit)
        return jsonify({"results": results, "count": len(results), "query": query})
    except Exception as exc:
        current_app.logger.error("ethos search_persons error: %s", exc, exc_info=True)
        return _error(str(exc), "ETHOS_ERROR", 500)
