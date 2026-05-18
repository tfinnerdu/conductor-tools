"""JQ Lab routes — /api/v1/jq/*"""
import json
import uuid

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient
from app.models.jq_expression import JqExpression
from app import db

jq_lab_bp = Blueprint("jq_lab", __name__, url_prefix="/api/v1/jq")


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


@jq_lab_bp.route("/evaluate", methods=["POST"])
def evaluate():
    """Evaluate a jq expression against a JSON payload."""
    try:
        import jq as jq_lib

        body = request.get_json(force=True) or {}
        expression = body.get("expression", "")
        input_data = body.get("input", {})

        if not expression:
            return _error("expression is required", "VALIDATION_ERROR")

        # Accept either a dict or a JSON string
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError as parse_err:
                return jsonify({"result": None, "error": f"Invalid JSON input: {parse_err}"}), 400

        try:
            result = jq_lib.first(expression, input_data)
            return jsonify({"result": result, "error": None})
        except Exception as jq_err:
            return jsonify({"result": None, "error": str(jq_err)})

    except ImportError:
        return _error("jq library not installed", "DEPENDENCY_ERROR", 500)
    except Exception as exc:
        current_app.logger.error("evaluate jq error: %s", exc, exc_info=True)
        return _error(str(exc), "JQ_ERROR", 500)


@jq_lab_bp.route("/load-from-execution", methods=["GET"])
def load_from_execution():
    """Load task output from a real Conductor execution."""
    workflow_id = request.args.get("workflowId", "")
    task_ref = request.args.get("taskRef", "")
    task_index = request.args.get("taskIndex")

    if not workflow_id:
        return _error("workflowId is required", "VALIDATION_ERROR")

    try:
        client = ConductorClient()
        execution = client.get_execution(workflow_id, include_tasks=True)
        tasks = execution.get("tasks", [])

        if not tasks:
            return jsonify({"found": False, "workflowId": workflow_id, "taskRef": task_ref, "data": {}})

        target_task = None
        if task_ref:
            for t in tasks:
                if t.get("referenceTaskName") == task_ref or t.get("taskReferenceName") == task_ref:
                    target_task = t
                    break
        elif task_index is not None:
            idx = int(task_index)
            if 0 <= idx < len(tasks):
                target_task = tasks[idx]
        else:
            # Default to last completed task
            for t in reversed(tasks):
                if t.get("status") == "COMPLETED":
                    target_task = t
                    break
            if target_task is None and tasks:
                target_task = tasks[-1]

        if target_task is None:
            return jsonify({"found": False, "workflowId": workflow_id, "taskRef": task_ref, "data": {}})

        output_data = target_task.get("outputData", {})
        return jsonify({
            "found": True,
            "workflowId": workflow_id,
            "taskId": target_task.get("taskId"),
            "taskType": target_task.get("taskType"),
            "taskRef": target_task.get("referenceTaskName", target_task.get("taskReferenceName")),
            "status": target_task.get("status"),
            "data": output_data,
        })

    except Exception as exc:
        current_app.logger.error("load_from_execution error: %s", exc, exc_info=True)
        return _error(str(exc), "EXECUTION_ERROR", 500)


@jq_lab_bp.route("/expressions", methods=["GET"])
def list_expressions():
    """List all saved JQ expressions from the library."""
    try:
        tag = request.args.get("tag", "")
        resource = request.args.get("resource", "")

        query = JqExpression.query
        if tag:
            query = query.filter(JqExpression.tags.contains(tag))
        if resource:
            query = query.filter(JqExpression.resource_name == resource)

        expressions = query.order_by(JqExpression.use_count.desc()).all()
        return jsonify([e.to_dict() for e in expressions])
    except Exception as exc:
        current_app.logger.error("list_expressions error: %s", exc, exc_info=True)
        return _error(str(exc), "DB_ERROR", 500)


@jq_lab_bp.route("/expressions", methods=["POST"])
def save_expression():
    """Save a JQ expression to the library."""
    try:
        body = request.get_json(force=True) or {}
        name = body.get("name", "").strip()
        expression = body.get("expression", "").strip()

        if not name:
            return _error("name is required", "VALIDATION_ERROR")
        if not expression:
            return _error("expression is required", "VALIDATION_ERROR")

        expr = JqExpression(
            name=name,
            description=body.get("description", ""),
            expression=expression,
            resource_name=body.get("resourceName", ""),
            use_case=body.get("useCase", ""),
            created_by=body.get("createdBy", "user"),
            tags=body.get("tags", ""),
        )
        db.session.add(expr)
        db.session.commit()
        return jsonify(expr.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("save_expression error: %s", exc, exc_info=True)
        return _error(str(exc), "DB_ERROR", 500)


@jq_lab_bp.route("/format-as-conductor-task", methods=["POST"])
def format_as_conductor_task():
    """Wrap a jq expression as a Conductor JSON_JQ_TRANSFORM task definition snippet."""
    try:
        body = request.get_json(force=True) or {}
        expression = body.get("expression", "").strip()
        task_ref = body.get("taskRef", "jq_transform_ref").strip()
        task_name = body.get("taskName", "jq_transform").strip()
        input_key = body.get("inputKey", "input").strip()

        if not expression:
            return _error("expression is required", "VALIDATION_ERROR")

        task_json = {
            "name": task_name,
            "taskReferenceName": task_ref,
            "type": "JSON_JQ_TRANSFORM",
            "inputParameters": {
                input_key: "${workflow.input}",
                "queryExpression": expression,
            },
        }

        return jsonify({"task": task_json, "json": json.dumps(task_json, indent=2)})
    except Exception as exc:
        current_app.logger.error("format_as_conductor_task error: %s", exc, exc_info=True)
        return _error(str(exc), "FORMAT_ERROR", 500)
