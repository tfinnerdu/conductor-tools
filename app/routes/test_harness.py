"""Test Harness routes — /api/v1/test-harness/*

Workflow Test Harness: run workflow definitions against Conductor's workflow
test endpoint with caller-supplied task mock outputs. Requires a live
Conductor — there is no in-process simulation fallback.
"""
import requests

from flask import Blueprint, current_app, jsonify, request

from app.conductor_client import ConductorClient
from app.models.test_preset import TestPreset
from app import db
from app.utils.responses import error_response

test_harness_bp = Blueprint("test_harness", __name__, url_prefix="/api/v1/test-harness")


# ---------------------------------------------------------------------------
# Built-in presets (returned when no DB rows exist for a preset name)
# ---------------------------------------------------------------------------

_BUILTIN_PRESETS = [
    {
        "name": "Person created in Colleague",
        "description": "Minimal Ethos persons payload simulating a new person created in Colleague.",
        "workflow_name": "student_enrollment",
        "input": {
            "sis_id": "SIS123456",
            "guid": "11111111-1111-1111-1111-111111111111",
            "firstName": "Alex",
            "lastName": "Student",
            "dateOfBirth": "2000-01-15",
        },
        "task_mocks": {
            "ethos_get_person_ref": {
                "outputData": {
                    "person": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "names": [{"firstName": "Alex", "lastName": "Student"}],
                        "credentials": [{"type": "colleaguePersonId", "value": "SIS123456"}],
                    }
                }
            },
            "enroll_ref": {
                "outputData": {"enrolled": True, "enrollmentId": "ENR-001"}
            },
        },
    },
    {
        "name": "Person address updated",
        "description": "Simulates an address-change event flowing through Conductor.",
        "workflow_name": "student_enrollment",
        "input": {
            "sis_id": "SIS123456",
            "guid": "22222222-2222-2222-2222-222222222222",
            "changeType": "ADDRESS_UPDATE",
            "address": {
                "streetAddress": "1 Doane Ave",
                "city": "Crete",
                "state": "NE",
                "zip": "68333",
            },
        },
        "task_mocks": {
            "ethos_get_person_ref": {
                "outputData": {
                    "person": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "addresses": [
                            {
                                "type": "home",
                                "streetAddress": "1 Doane Ave",
                                "city": "Crete",
                                "state": "NE",
                            }
                        ],
                    }
                }
            },
            "enroll_ref": {"outputData": {"updated": True}},
        },
    },
    {
        "name": "Application submitted",
        "description": "Admissions application submitted through the portal.",
        "workflow_name": "financial_aid_processing",
        "input": {
            "applicantId": "APP-7890",
            "programCode": "BSCS",
            "term": "2024FA",
            "submittedAt": "2024-03-01T10:00:00Z",
        },
        "task_mocks": {
            "validate_order_ref": {
                "outputData": {"valid": True, "applicationId": "APP-7890"}
            },
            "charge_payment_ref": {
                "outputData": {"charged": True, "amount": 40.00, "receiptId": "REC-001"}
            },
        },
    },
    {
        "name": "Ethos 404 error",
        "description": "What happens when ethos_get_by_id cannot find the record (404 response).",
        "workflow_name": "student_enrollment",
        "input": {
            "sis_id": "SIS_NOTFOUND",
            "guid": "00000000-0000-0000-0000-000000000000",
        },
        "task_mocks": {
            "ethos_get_person_ref": {
                "outputData": {
                    "error": "HTTP_404",
                    "message": "Person not found in Ethos",
                    "statusCode": 404,
                }
            }
        },
    },
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@test_harness_bp.get("/workflows")
def list_workflows():
    """List workflow names and versions from Conductor (or mock)."""
    try:
        client = ConductorClient()
        defs = client.list_workflow_definitions()
        # Deduplicate to name+version pairs
        seen = set()
        result = []
        for d in defs:
            key = (d.get("name"), d.get("version"))
            if key not in seen:
                seen.add(key)
                result.append(
                    {
                        "name": d.get("name"),
                        "version": d.get("version"),
                        "description": d.get("description", ""),
                    }
                )
        current_app.logger.info("test_harness list_workflows: count=%d", len(result))
        return jsonify({"workflows": result})
    except Exception as exc:
        current_app.logger.error("list_workflows error: %s", exc, exc_info=True)
        return error_response(str(exc), "LIST_ERROR", 500)


@test_harness_bp.get("/workflows/<name>/tasks")
def get_workflow_tasks(name: str):
    """Return task reference names for a workflow definition.

    Query params:
      - version (int, optional — defaults to latest)
    """
    version_str = request.args.get("version")
    version = int(version_str) if version_str else None

    try:
        client = ConductorClient()
        defn = client.get_workflow_definition(name, version=version)
        tasks = defn.get("tasks", [])
        task_refs = [
            {
                "ref_name": t.get("taskReferenceName", t.get("name")),
                "task_type": t.get("type", "SIMPLE"),
                "task_name": t.get("name"),
            }
            for t in tasks
        ]
        current_app.logger.info(
            "get_workflow_tasks: name=%s version=%s tasks=%d", name, version, len(task_refs)
        )
        return jsonify(
            {
                "name": name,
                "version": defn.get("version"),
                "tasks": task_refs,
            }
        )
    except Exception as exc:
        current_app.logger.error("get_workflow_tasks error: %s", exc, exc_info=True)
        return error_response(str(exc), "TASKS_ERROR", 500)


@test_harness_bp.post("/run")
def run_test():
    """Run a workflow test, either against live Conductor or in simulation mode.

    Body: {
        workflow_name: str,
        version: int (optional),
        input: {},
        task_mocks: { ref_name: { outputData: {} } }
    }
    """
    body = request.get_json(force=True) or {}
    workflow_name = (body.get("workflow_name") or "").strip()
    version = body.get("version")
    workflow_input = body.get("input") or {}
    task_mocks = body.get("task_mocks") or {}

    if not workflow_name:
        return error_response("workflow_name is required", "VALIDATION_ERROR")

    try:
        client = ConductorClient()

        # POST to Conductor's workflow test endpoint.
        payload = {
            "name": workflow_name,
            "version": version,
            "input": workflow_input,
            "taskRefToMockOutput": task_mocks,
        }
        resp = requests.post(
            f"{client.base_url}/api/workflow/test",
            headers=client.get_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        current_app.logger.info(
            "test_harness run: workflow=%s status=%s",
            workflow_name,
            result.get("status"),
        )
        return jsonify(result)

    except Exception as exc:
        current_app.logger.error("run_test error: %s", exc, exc_info=True)
        return error_response(str(exc), "RUN_ERROR", 500)


@test_harness_bp.get("/presets")
def get_presets():
    """Return built-in presets plus any user-saved presets from the database."""
    try:
        db_presets = TestPreset.query.order_by(TestPreset.created_at.desc()).all()
        db_list = [p.to_dict() for p in db_presets]

        # Combine built-ins (first) then DB entries
        builtins = [
            {
                "id": None,
                "name": p["name"],
                "description": p["description"],
                "workflowName": p["workflow_name"],
                "input": p["input"],
                "taskMocks": p["task_mocks"],
                "createdBy": "system",
                "createdAt": None,
                "builtin": True,
            }
            for p in _BUILTIN_PRESETS
        ]

        return jsonify({"presets": builtins + db_list})
    except Exception as exc:
        current_app.logger.error("get_presets error: %s", exc, exc_info=True)
        return error_response(str(exc), "PRESET_ERROR", 500)


@test_harness_bp.post("/presets")
def save_preset():
    """Save a custom test preset to the database.

    Body: { name, description, workflow_name, input, task_mocks, created_by }
    """
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return error_response("name is required", "VALIDATION_ERROR")

    workflow_name = (body.get("workflow_name") or body.get("workflowName") or "").strip()

    try:
        preset = TestPreset(
            name=name,
            description=body.get("description", ""),
            workflow_name=workflow_name,
            input_data=body.get("input") or {},
            task_mocks=body.get("task_mocks") or body.get("taskMocks") or {},
            created_by=body.get("created_by") or body.get("createdBy") or "user",
        )
        db.session.add(preset)
        db.session.commit()
        current_app.logger.info("save_preset: name=%s id=%d", preset.name, preset.id)
        return jsonify(preset.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("save_preset error: %s", exc, exc_info=True)
        return error_response(str(exc), "PRESET_SAVE_ERROR", 500)
