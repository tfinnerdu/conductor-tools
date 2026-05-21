"""Batches routes — /api/v1/batches/*"""
import csv
import io
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, Response

from app.conductor_client import ConductorClient
from app.models.migration_batch import MigrationBatch
from app import db
from app.utils.responses import error_response

batches_bp = Blueprint("batches", __name__, url_prefix="/api/v1/batches")


@batches_bp.route("", methods=["GET"])
def list_batches():
    """List all migration batches."""
    try:
        batches = MigrationBatch.query.order_by(MigrationBatch.started_at.desc()).all()
        return jsonify([b.to_dict() for b in batches])
    except Exception as exc:
        current_app.logger.error("list_batches error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)


@batches_bp.route("", methods=["POST"])
def create_batch():
    """Create a new migration batch."""
    try:
        body = request.get_json(force=True) or {}
        name = body.get("name", "").strip()
        workflow_name = body.get("workflowName", "").strip()

        if not name:
            return error_response("name is required", "VALIDATION_ERROR")
        if not workflow_name:
            return error_response("workflowName is required", "VALIDATION_ERROR")

        batch = MigrationBatch(
            name=name,
            workflow_name=workflow_name,
            correlation_id_prefix=body.get("correlationIdPrefix", ""),
            total_expected=int(body.get("totalExpected", 0)),
            created_by=body.get("createdBy", "user"),
            notes=body.get("notes", ""),
        )
        db.session.add(batch)
        db.session.commit()
        return jsonify(batch.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("create_batch error: %s", exc, exc_info=True)
        return error_response(str(exc), "DB_ERROR", 500)


@batches_bp.route("/<int:batch_id>/status", methods=["GET"])
def batch_status(batch_id: int):
    """Poll batch status by paginating through all Conductor results."""
    try:
        batch = db.session.get(MigrationBatch, batch_id)
        if not batch:
            return error_response("Batch not found", "NOT_FOUND", 404)

        client = ConductorClient()
        page_size = 100
        start = 0
        all_executions = []

        # Paginate until we have fetched all results
        while True:
            result = client.search(
                workflow_type=batch.workflow_name,
                query=f"correlationId STARTS_WITH '{batch.correlation_id_prefix}'" if batch.correlation_id_prefix else "",
                start=start,
                size=page_size,
            )
            page_results = result.get("results", [])
            total_hits = result.get("totalHits", 0)
            all_executions.extend(page_results)

            if len(page_results) < page_size or len(all_executions) >= total_hits:
                break
            start += page_size

        # Tally status counts
        status_counts = {}
        for ex in all_executions:
            s = ex.get("status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

        total_found = len(all_executions)
        completed = status_counts.get("COMPLETED", 0)
        failed = status_counts.get("FAILED", 0)
        running = status_counts.get("RUNNING", 0) + status_counts.get("PAUSED", 0)
        total_expected = batch.total_expected or total_found

        progress_pct = round((completed / total_expected * 100) if total_expected else 0, 1)

        return jsonify({
            "batchId": batch.id,
            "name": batch.name,
            "workflowName": batch.workflow_name,
            "totalExpected": total_expected,
            "totalFound": total_found,
            "completed": completed,
            "failed": failed,
            "running": running,
            "progressPercent": progress_pct,
            "statusCounts": status_counts,
        })
    except Exception as exc:
        current_app.logger.error("batch_status error: %s", exc, exc_info=True)
        return error_response(str(exc), "BATCH_STATUS_ERROR", 500)


@batches_bp.route("/<int:batch_id>/retry-failures", methods=["POST"])
def retry_failures(batch_id: int):
    """Retry all FAILED workflow executions in a batch."""
    try:
        batch = db.session.get(MigrationBatch, batch_id)
        if not batch:
            return error_response("Batch not found", "NOT_FOUND", 404)

        client = ConductorClient()
        page_size = 100
        start = 0
        retried = 0
        errors = []

        while True:
            result = client.search(
                workflow_type=batch.workflow_name,
                status="FAILED",
                query=f"correlationId STARTS_WITH '{batch.correlation_id_prefix}'" if batch.correlation_id_prefix else "",
                start=start,
                size=page_size,
            )
            page_results = result.get("results", [])
            total_hits = result.get("totalHits", 0)

            for ex in page_results:
                wf_id = ex.get("workflowId")
                if wf_id:
                    try:
                        client.retry_workflow(wf_id)
                        retried += 1
                    except Exception as retry_err:
                        errors.append({"workflowId": wf_id, "error": str(retry_err)})

            if len(page_results) < page_size or (start + len(page_results)) >= total_hits:
                break
            start += page_size

        return jsonify({
            "batchId": batch_id,
            "retriedCount": retried,
            "errorCount": len(errors),
            "errors": errors[:20],  # Cap error list to avoid huge responses
        })
    except Exception as exc:
        current_app.logger.error("retry_failures error: %s", exc, exc_info=True)
        return error_response(str(exc), "RETRY_ERROR", 500)


@batches_bp.route("/<int:batch_id>/export", methods=["GET"])
def export_batch(batch_id: int):
    """Export failed executions in a batch as CSV."""
    try:
        batch = db.session.get(MigrationBatch, batch_id)
        if not batch:
            return error_response("Batch not found", "NOT_FOUND", 404)

        client = ConductorClient()
        page_size = 100
        start = 0
        failed_executions = []

        while True:
            result = client.search(
                workflow_type=batch.workflow_name,
                status="FAILED",
                query=f"correlationId STARTS_WITH '{batch.correlation_id_prefix}'" if batch.correlation_id_prefix else "",
                start=start,
                size=page_size,
            )
            page_results = result.get("results", [])
            total_hits = result.get("totalHits", 0)
            failed_executions.extend(page_results)

            if len(page_results) < page_size or len(failed_executions) >= total_hits:
                break
            start += page_size

        output = io.StringIO()
        fieldnames = [
            "workflowId", "workflowType", "status", "correlationId",
            "startTime", "endTime", "version",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in failed_executions:
            row = dict(row)
            for tf in ("startTime", "endTime"):
                val = row.get(tf)
                if isinstance(val, (int, float)) and val > 0:
                    row[tf] = datetime.utcfromtimestamp(val / 1000).isoformat() + "Z"
            writer.writerow(row)

        output.seek(0)
        safe_name = batch.name.replace(" ", "_").replace("/", "-")
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=batch_{batch_id}_{safe_name}_failures.csv"
            },
        )
    except Exception as exc:
        current_app.logger.error("export_batch error: %s", exc, exc_info=True)
        return error_response(str(exc), "EXPORT_ERROR", 500)
