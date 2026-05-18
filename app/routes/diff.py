"""Diff routes — /api/v1/diff/*"""
import difflib
import json
import uuid

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient

diff_bp = Blueprint("diff", __name__, url_prefix="/api/v1/diff")


def _error(message: str, code: str, status: int = 400):
    return jsonify({"error": message, "code": code, "request_id": str(uuid.uuid4())}), status


def _render_diff_html(lines_a: list, lines_b: list) -> list:
    """Produce a list of diff line objects with CSS class hints.

    Each item: {"line": str, "type": "added"|"removed"|"context"|"header"}
    """
    diff = difflib.unified_diff(lines_a, lines_b, lineterm="")
    rendered = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            rendered.append({"line": line, "type": "header"})
        elif line.startswith("@@"):
            rendered.append({"line": line, "type": "header"})
        elif line.startswith("+"):
            rendered.append({"line": line, "type": "added"})
        elif line.startswith("-"):
            rendered.append({"line": line, "type": "removed"})
        else:
            rendered.append({"line": line, "type": "context"})
    return rendered


def _significant_changes(diff_lines: list) -> list:
    """Filter diff lines to only task-level changes (name, type, inputParameters)."""
    significant_keys = {"name", "taskReferenceName", "type", "inputParameters"}
    result = []
    for item in diff_lines:
        line = item["line"]
        if item["type"] in ("added", "removed"):
            # Check if the line contains a significant key
            if any(f'"{k}"' in line for k in significant_keys):
                result.append(item)
        elif item["type"] == "header":
            result.append(item)
    return result


def _extract_task_lines(definition: dict) -> list:
    """Extract just the tasks array as indented JSON lines."""
    tasks = definition.get("tasks", [])
    return json.dumps(tasks, indent=2).splitlines(keepends=False)


@diff_bp.route("/workflows", methods=["GET"])
def list_workflows():
    """List all workflow names and their available versions."""
    try:
        client = ConductorClient()
        definitions = client.list_workflow_definitions()

        # Group by name
        by_name = {}
        for defn in definitions:
            name = defn.get("name")
            version = defn.get("version", 1)
            if name not in by_name:
                by_name[name] = {"name": name, "versions": [], "description": defn.get("description", "")}
            by_name[name]["versions"].append(version)

        result = sorted(by_name.values(), key=lambda x: x["name"])
        return jsonify(result)
    except Exception as exc:
        current_app.logger.error("list_workflows error: %s", exc, exc_info=True)
        return _error(str(exc), "LIST_ERROR", 500)


@diff_bp.route("/workflow", methods=["POST"])
def diff_workflow():
    """Side-by-side version diff for a workflow."""
    try:
        body = request.get_json(force=True) or {}
        workflow_name = body.get("workflowName", "").strip()
        version_a = body.get("versionA")
        version_b = body.get("versionB")
        mode = body.get("mode", "full")  # full | tasks | significant

        if not workflow_name:
            return _error("workflowName is required", "VALIDATION_ERROR")
        if version_a is None or version_b is None:
            return _error("versionA and versionB are required", "VALIDATION_ERROR")

        client = ConductorClient()
        def_a = client.get_workflow_definition(workflow_name, version=version_a)
        def_b = client.get_workflow_definition(workflow_name, version=version_b)

        if mode == "tasks":
            lines_a = _extract_task_lines(def_a)
            lines_b = _extract_task_lines(def_b)
        else:
            lines_a = json.dumps(def_a, indent=2).splitlines()
            lines_b = json.dumps(def_b, indent=2).splitlines()

        diff_lines = _render_diff_html(lines_a, lines_b)

        if mode == "significant":
            diff_lines = _significant_changes(diff_lines)

        added = sum(1 for d in diff_lines if d["type"] == "added")
        removed = sum(1 for d in diff_lines if d["type"] == "removed")

        return jsonify({
            "workflowName": workflow_name,
            "versionA": version_a,
            "versionB": version_b,
            "mode": mode,
            "diffLines": diff_lines,
            "summary": {
                "addedLines": added,
                "removedLines": removed,
                "changedLines": min(added, removed),
            },
        })
    except Exception as exc:
        current_app.logger.error("diff_workflow error: %s", exc, exc_info=True)
        return _error(str(exc), "DIFF_ERROR", 500)


@diff_bp.route("/dependency-map", methods=["GET"])
def dependency_map():
    """Return the full dependency graph: which workflows use which task types."""
    try:
        client = ConductorClient()
        definitions = client.list_workflow_definitions()

        # For each workflow, fetch its full definition to inspect tasks
        graph = {}
        seen_names = set()

        for defn in definitions:
            name = defn.get("name")
            version = defn.get("version", 1)
            key = f"{name}@v{version}"
            if key in seen_names:
                continue
            seen_names.add(key)

            # Use the tasks from the listing (may be empty) or fetch full definition
            tasks = defn.get("tasks", [])
            if not tasks:
                full = client.get_workflow_definition(name, version=version)
                tasks = full.get("tasks", [])

            task_types = list({t.get("name", t.get("taskReferenceName", "")) for t in tasks if t.get("name")})
            graph[key] = {
                "workflowName": name,
                "version": version,
                "taskTypes": sorted(task_types),
            }

        return jsonify({
            "nodes": list(graph.values()),
            "totalWorkflows": len(graph),
        })
    except Exception as exc:
        current_app.logger.error("dependency_map error: %s", exc, exc_info=True)
        return _error(str(exc), "DEPENDENCY_ERROR", 500)


@diff_bp.route("/impact", methods=["POST"])
def impact_analysis():
    """Analyze which workflows are impacted by a change to a task type."""
    try:
        body = request.get_json(force=True) or {}
        task_type = body.get("taskType", "").strip()

        if not task_type:
            return _error("taskType is required", "VALIDATION_ERROR")

        client = ConductorClient()
        definitions = client.list_workflow_definitions()

        impacted = []
        seen_names = set()

        for defn in definitions:
            name = defn.get("name")
            version = defn.get("version", 1)
            key = f"{name}@v{version}"
            if key in seen_names:
                continue
            seen_names.add(key)

            tasks = defn.get("tasks", [])
            if not tasks:
                full = client.get_workflow_definition(name, version=version)
                tasks = full.get("tasks", [])

            task_names = [t.get("name", "") for t in tasks]
            if task_type in task_names:
                # Find which references use this task type
                refs = [
                    t.get("taskReferenceName", t.get("name", ""))
                    for t in tasks
                    if t.get("name") == task_type
                ]
                impacted.append({
                    "workflowName": name,
                    "version": version,
                    "taskReferences": refs,
                })

        return jsonify({
            "taskType": task_type,
            "impactedWorkflows": impacted,
            "impactedCount": len(impacted),
        })
    except Exception as exc:
        current_app.logger.error("impact_analysis error: %s", exc, exc_info=True)
        return _error(str(exc), "IMPACT_ERROR", 500)
