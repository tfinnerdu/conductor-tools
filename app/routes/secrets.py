"""Secrets routes — /api/v1/secrets/*"""
import json
import uuid

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient

secrets_bp = Blueprint("secrets", __name__, url_prefix="/api/v1/secrets")


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


# Pattern used in Conductor workflow definitions for secret references
_SECRET_PATTERN = "__secret"


@secrets_bp.route("", methods=["GET"])
def list_secrets():
    """List all secret names from Conductor."""
    try:
        client = ConductorClient()
        names = client.list_secrets()
        return jsonify({"secrets": names, "count": len(names)})
    except Exception as exc:
        current_app.logger.error("list_secrets error: %s", exc, exc_info=True)
        return _error(str(exc), "SECRETS_ERROR", 500)


@secrets_bp.route("/<name>", methods=["POST"])
def set_secret(name: str):
    """Create or update a secret value."""
    try:
        body = request.get_json(force=True) or {}
        value = body.get("value")
        if value is None:
            return _error("value is required in request body", "VALIDATION_ERROR")

        client = ConductorClient()
        client.set_secret(name, str(value))
        return jsonify({"name": name, "updated": True})
    except Exception as exc:
        current_app.logger.error("set_secret error: %s", exc, exc_info=True)
        return _error(str(exc), "SET_SECRET_ERROR", 500)


@secrets_bp.route("/<name>", methods=["DELETE"])
def delete_secret(name: str):
    """Delete a secret by name."""
    try:
        client = ConductorClient()
        client.delete_secret(name)
        return jsonify({"name": name, "deleted": True})
    except Exception as exc:
        current_app.logger.error("delete_secret error: %s", exc, exc_info=True)
        return _error(str(exc), "DELETE_SECRET_ERROR", 500)


@secrets_bp.route("/<name>/usages", methods=["GET"])
def secret_usages(name: str):
    """Find which workflow definitions reference a given secret name."""
    try:
        client = ConductorClient()
        definitions = client.list_workflow_definitions()

        usages = []
        seen = set()

        for defn in definitions:
            wf_name = defn.get("name")
            version = defn.get("version", 1)
            key = f"{wf_name}@v{version}"
            if key in seen:
                continue
            seen.add(key)

            # Fetch full definition to inspect inputParameters deeply
            tasks = defn.get("tasks", [])
            if not tasks:
                full = client.get_workflow_definition(wf_name, version=version)
                tasks = full.get("tasks", [])
                defn = full

            # Serialize the whole definition and search for secret references
            defn_str = json.dumps(defn)
            # Conductor secret references look like: ${secret.SECRET_NAME} or __secret.SECRET_NAME
            if name in defn_str:
                # Find specific task references
                referencing_tasks = []
                for task in tasks:
                    task_str = json.dumps(task)
                    if name in task_str:
                        referencing_tasks.append({
                            "taskType": task.get("name", ""),
                            "taskRef": task.get("taskReferenceName", ""),
                        })

                usages.append({
                    "workflowName": wf_name,
                    "version": version,
                    "referencingTasks": referencing_tasks,
                })

        return jsonify({
            "secretName": name,
            "usages": usages,
            "usageCount": len(usages),
        })
    except Exception as exc:
        current_app.logger.error("secret_usages error: %s", exc, exc_info=True)
        return _error(str(exc), "USAGES_ERROR", 500)
