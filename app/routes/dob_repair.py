"""DOB Repair routes — /api/v1/dob-repair/*

Review console for PD0002124 (Instant Enrollment stores DOB one day early for
registrants whose browser timezone is east of the Central-time server). Runs
the detector (app/dob_detector.py) against a PERSON export, surfaces a
human-gated review queue, and exports approved corrections as CSV.

This blueprint never writes to Colleague, Ethos, or NAE. It only persists the
reviewer's decision (accept/reject/defer) in Conductor Companion's own
database and exports an approved-corrections CSV for a separate, sanctioned
apply step outside this tool.

Analysis state (the last-computed candidate list) is held in a module-level,
in-memory dict — recomputed on each /analyze call. This mirrors the existing
in-memory event buffer in app/ethos_provider.py: fine for a single-process,
low-traffic internal review tool, not meant to survive a process restart.
Reviewer decisions, unlike the analysis itself, are durable (see
app/models/dob_decision.py) and are re-joined against whatever candidate list
is currently in memory.
"""
import csv
import io
import os
from datetime import datetime, date

from flask import Blueprint, Response, current_app, jsonify, request

from app import db
from app import dob_detector as detector
from app import dob_sql_source
from app.models.dob_decision import VALID_DECISIONS, DobDecision
from app.utils.responses import error_response

dob_repair_bp = Blueprint("dob_repair", __name__, url_prefix="/api/v1/dob-repair")

_STATE = {
    "result": None,        # detector.AnalysisResult
    "by_id": {},            # candidate_id -> detector.Candidate
    "source": None,
    "analyzed_at": None,
    "identity_threshold": detector.IDENTITY_THRESHOLD,
}


def _configured_input_path() -> str:
    return os.environ.get("DOB_RECONCILE_INPUT_CSV", "").strip()


def _store_result(result, source: str, identity_threshold: int) -> None:
    _STATE["result"] = result
    _STATE["by_id"] = {c.candidate_id: c for c in result.candidates}
    _STATE["source"] = source
    _STATE["analyzed_at"] = datetime.utcnow().isoformat() + "Z"
    _STATE["identity_threshold"] = identity_threshold


@dob_repair_bp.post("/analyze")
def analyze():
    """Run the detector against an uploaded CSV, or the configured path.

    Multipart form: csv_file (optional), threshold (optional, default 6).
    If csv_file is omitted, falls back to DOB_RECONCILE_INPUT_CSV.
    """
    try:
        threshold = int(request.form.get("threshold", detector.IDENTITY_THRESHOLD))
    except ValueError:
        return error_response("threshold must be an integer", "VALIDATION_ERROR")

    upload = request.files.get("csv_file")
    try:
        if upload and upload.filename:
            text = upload.stream.read().decode("utf-8-sig")
            records = detector.load_records(io.StringIO(text))
            source = upload.filename
        else:
            configured_path = _configured_input_path()
            if not configured_path:
                return error_response(
                    "No csv_file uploaded and DOB_RECONCILE_INPUT_CSV is not configured",
                    "NO_INPUT",
                )
            records = detector.load_records(configured_path)
            source = configured_path
    except FileNotFoundError:
        return error_response(
            f"Configured input path not found: {_configured_input_path()}",
            "NOT_FOUND",
            404,
        )
    except Exception as exc:
        current_app.logger.error("dob_repair analyze parse error: %s", exc, exc_info=True)
        return error_response(f"Could not parse CSV: {exc}", "PARSE_ERROR")

    result = detector.analyze(records, identity_threshold=threshold)
    _store_result(result, source, threshold)

    current_app.logger.info(
        "dob_repair analyze: source=%s %s", source, result.summary
    )
    return jsonify({
        "source": source,
        "analyzedAt": _STATE["analyzed_at"],
        "identityThreshold": threshold,
        "summary": result.summary,
    })


@dob_repair_bp.post("/analyze/sql")
def analyze_sql():
    """Run the detector against DOB_RECONCILE_SQL_FILE, fetched live via SQL Server.

    Body (optional JSON): {threshold}. The query itself is not accepted here —
    it is drafted and owned by whoever configures DOB_RECONCILE_SQL_FILE on
    the server; this endpoint only runs whatever is currently in that file.
    """
    body = request.get_json(silent=True) or {}
    try:
        threshold = int(body.get("threshold", detector.IDENTITY_THRESHOLD))
    except (TypeError, ValueError):
        return error_response("threshold must be an integer", "VALIDATION_ERROR")

    if not dob_sql_source.is_configured():
        return error_response(
            "SQL fetch is not configured — set DOB_RECONCILE_SQL_FILE and "
            "DOB_RECONCILE_DB_SERVER/DOB_RECONCILE_DB_NAME",
            "NOT_CONFIGURED",
        )

    try:
        records = dob_sql_source.fetch_records()
    except ValueError as exc:
        # Read-only guard rejected the configured query, or it's empty.
        return error_response(str(exc), "UNSAFE_QUERY")
    except RuntimeError as exc:
        return error_response(str(exc), "NOT_CONFIGURED")
    except Exception as exc:
        current_app.logger.error("dob_repair analyze_sql error: %s", exc, exc_info=True)
        return error_response(f"SQL fetch failed: {exc}", "SQL_ERROR", 502)

    source = f"sql:{dob_sql_source.sql_file_path()}"
    result = detector.analyze(records, identity_threshold=threshold)
    _store_result(result, source, threshold)

    current_app.logger.info(
        "dob_repair analyze via SQL: rows=%d %s", len(records), result.summary
    )
    return jsonify({
        "source": source,
        "analyzedAt": _STATE["analyzed_at"],
        "identityThreshold": threshold,
        "summary": result.summary,
    })


@dob_repair_bp.get("/status")
def status():
    """Whether an analysis has run, and which server-side input sources are configured."""
    result = _STATE["result"]
    return jsonify({
        "analyzed": result is not None,
        "analyzedAt": _STATE["analyzed_at"],
        "source": _STATE["source"],
        "identityThreshold": _STATE["identity_threshold"],
        "summary": result.summary if result else None,
        "configuredInputPath": bool(_configured_input_path()),
        "sqlConfigured": dob_sql_source.is_configured(),
    })


def _decisions_by_candidate() -> dict:
    return {d.candidate_id: d.to_dict() for d in DobDecision.query.all()}


@dob_repair_bp.get("/candidates")
def list_candidates():
    """Candidate queue, elevated-risk worklist, and unparseable DOBs from the
    most recent analysis, each candidate joined with its reviewer decision
    (if any)."""
    result = _STATE["result"]
    if result is None:
        return error_response("No analysis has been run yet", "NOT_ANALYZED", 404)

    try:
        decisions = _decisions_by_candidate()
        candidates = []
        for c in result.candidates:
            row = c.as_row()
            row["decision"] = decisions.get(c.candidate_id)
            candidates.append(row)

        elevated = [
            {
                "personId": r.person_id,
                "name": f"{r.first_name} {r.last_name}".strip(),
                "dob": r.birth_date.isoformat() if r.birth_date else "",
                "state": r.state,
            }
            for r in result.elevated_risk
        ]
        unparseable = [
            {
                "personId": r.person_id,
                "name": f"{r.first_name} {r.last_name}".strip(),
                "rawBirthDate": r.raw_birth_date,
            }
            for r in result.unparseable_dob
        ]

        return jsonify({
            "summary": result.summary,
            "candidates": candidates,
            "elevatedRisk": elevated,
            "unparseableDob": unparseable,
        })
    except Exception as exc:
        current_app.logger.error("dob_repair list_candidates error: %s", exc, exc_info=True)
        return error_response(str(exc), "DOB_REPAIR_ERROR", 500)


@dob_repair_bp.post("/decision")
def record_decision():
    """Record a reviewer decision for one candidate pair.

    Body: {candidate_id, action, true_dob?, reviewer?, note?}
    For action="accept", true_dob must match one side of the pair — the
    reviewer is asserting which date is correct; the OTHER record is the one
    flagged as needing correction.
    """
    body = request.get_json(silent=True) or {}
    candidate_id = (body.get("candidate_id") or "").strip()
    action = (body.get("action") or "").strip().lower()
    true_dob_raw = (body.get("true_dob") or "").strip()
    reviewer = (body.get("reviewer") or "unknown").strip()
    note = (body.get("note") or "").strip()

    cand = _STATE["by_id"].get(candidate_id)
    if cand is None:
        return error_response("Unknown candidate_id — run /analyze first", "NOT_FOUND", 404)
    if action not in VALID_DECISIONS:
        return error_response(
            f"action must be one of {sorted(VALID_DECISIONS)}", "VALIDATION_ERROR"
        )

    corrected_person_id = corrected_from = corrected_to = None
    if action == "accept":
        chosen = detector.parse_date(true_dob_raw)
        if chosen is None:
            return error_response(
                "accept requires a valid true_dob matching one side of the pair",
                "VALIDATION_ERROR",
            )
        earlier, later = cand.record_a, cand.record_b
        if chosen == later.birth_date:
            corrected_person_id = earlier.person_id
            corrected_from = _iso(earlier.birth_date)
            corrected_to = _iso(later.birth_date)
        elif chosen == earlier.birth_date:
            corrected_person_id = later.person_id
            corrected_from = _iso(later.birth_date)
            corrected_to = _iso(earlier.birth_date)
        else:
            return error_response(
                "true_dob must match either the earlier or later record's DOB",
                "VALIDATION_ERROR",
            )

    try:
        existing = db.session.get(DobDecision, candidate_id)
        if existing is None:
            existing = DobDecision(candidate_id=candidate_id)
            db.session.add(existing)
        existing.action = action
        existing.corrected_person_id = corrected_person_id
        existing.corrected_from = corrected_from
        existing.corrected_to = corrected_to
        existing.reviewer = reviewer
        existing.decided_at = datetime.utcnow()
        existing.note = note
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("dob_repair record_decision error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)

    current_app.logger.info(
        "dob_repair decision: candidate=%s action=%s corrected=%s reviewer=%s",
        candidate_id, action, corrected_person_id, reviewer,
    )
    return jsonify({
        "candidateId": candidate_id,
        "action": action,
        "correctedPersonId": corrected_person_id,
        "correctedFrom": corrected_from,
        "correctedTo": corrected_to,
    })


@dob_repair_bp.get("/export/corrections")
def export_corrections():
    """CSV of approved corrections for a sanctioned apply step OUTSIDE this
    tool. This is the only output that should touch a write path, and only
    through a reviewed, audited channel (Ethos PUT or manual NAE correction)."""
    try:
        accepted = (
            DobDecision.query.filter(
                DobDecision.action == "accept",
                DobDecision.corrected_person_id.isnot(None),
            )
            .order_by(DobDecision.decided_at)
            .all()
        )

        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "person_id", "current_dob", "corrected_dob",
                "decided_by", "decided_at", "candidate_id", "note",
            ],
        )
        writer.writeheader()
        for d in accepted:
            writer.writerow({
                "person_id": d.corrected_person_id,
                "current_dob": d.corrected_from,
                "corrected_dob": d.corrected_to,
                "decided_by": d.reviewer,
                "decided_at": d.decided_at.isoformat() + "Z" if d.decided_at else "",
                "candidate_id": d.candidate_id,
                "note": d.note or "",
            })

        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=dob_corrections.csv"},
        )
    except Exception as exc:
        current_app.logger.error("dob_repair export_corrections error: %s", exc, exc_info=True)
        return error_response(str(exc), "EXPORT_ERROR", 500)


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else ""
