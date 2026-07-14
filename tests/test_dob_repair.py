"""Tests for DOB Repair routes — /api/v1/dob-repair/*"""
import io
import os

import pytest

from app.routes import dob_repair as dob_repair_routes

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "dob_sample_persons.csv")

# Deterministic candidate ids from the fixture (sorted person_id pair).
SMITH_HIGH = "1001__1002"     # HIGH: IE 4/2 vs authoritative 4/3
KING_HIGH = "3001__3002"      # HIGH: year-boundary shift
LEE_REVIEW = "5001__5002"     # REVIEW: IE record is the later date


@pytest.fixture(autouse=True)
def _reset_dob_state():
    """The analysis result lives in a module-level dict, not the per-test
    Flask app/db, so it must be reset between tests explicitly."""
    dob_repair_routes._STATE.update({
        "result": None, "by_id": {}, "source": None, "analyzed_at": None,
        "identity_threshold": dob_repair_routes.detector.IDENTITY_THRESHOLD,
    })
    yield
    dob_repair_routes._STATE.update({
        "result": None, "by_id": {}, "source": None, "analyzed_at": None,
        "identity_threshold": dob_repair_routes.detector.IDENTITY_THRESHOLD,
    })


def _upload(client, filename="dob_sample_persons.csv"):
    with open(FIXTURE, "rb") as fh:
        data = fh.read()
    return client.post(
        "/api/v1/dob-repair/analyze",
        data={"csv_file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


class TestStatus:
    def test_status_before_analysis(self, client):
        resp = client.get("/api/v1/dob-repair/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["analyzed"] is False
        assert data["configuredInputPath"] is False

    def test_candidates_before_analysis_returns_404(self, client):
        resp = client.get("/api/v1/dob-repair/candidates")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_ANALYZED"


class TestAnalyze:
    def test_no_file_and_no_configured_path_returns_400(self, client):
        resp = client.post("/api/v1/dob-repair/analyze", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "NO_INPUT"

    def test_upload_analyzes_and_returns_summary(self, client):
        resp = _upload(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "dob_sample_persons.csv"
        summary = data["summary"]
        assert summary["high"] == 2
        assert summary["medium"] == 1
        assert summary["review"] == 1
        assert summary["elevated_risk"] == 3

    def test_status_reflects_analysis(self, client):
        _upload(client)
        resp = client.get("/api/v1/dob-repair/status")
        data = resp.get_json()
        assert data["analyzed"] is True
        assert data["source"] == "dob_sample_persons.csv"

    def test_configured_path_fallback(self, client, monkeypatch):
        monkeypatch.setenv("DOB_RECONCILE_INPUT_CSV", FIXTURE)
        resp = client.post("/api/v1/dob-repair/analyze", data={}, content_type="multipart/form-data")
        assert resp.status_code == 200
        assert resp.get_json()["source"] == FIXTURE

    def test_configured_path_not_found(self, client, monkeypatch):
        monkeypatch.setenv("DOB_RECONCILE_INPUT_CSV", "/no/such/file.csv")
        resp = client.post("/api/v1/dob-repair/analyze", data={}, content_type="multipart/form-data")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"


class TestCandidates:
    def test_candidates_joined_with_no_decisions(self, client):
        _upload(client)
        resp = client.get("/api/v1/dob-repair/candidates")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = {c["candidate_id"] for c in data["candidates"]}
        assert SMITH_HIGH in ids
        assert KING_HIGH in ids
        assert LEE_REVIEW in ids
        smith = next(c for c in data["candidates"] if c["candidate_id"] == SMITH_HIGH)
        assert smith["bucket"] == "HIGH"
        assert smith["decision"] is None

    def test_elevated_risk_and_summary_present(self, client):
        _upload(client)
        resp = client.get("/api/v1/dob-repair/candidates")
        data = resp.get_json()
        elevated_ids = {r["personId"] for r in data["elevatedRisk"]}
        assert {"4001", "8001", "7001"}.issubset(elevated_ids)
        assert data["summary"]["total_records"] == 14


class TestDecision:
    def test_unknown_candidate_returns_404(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": "nope__nope", "action": "reject",
        })
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"

    def test_invalid_action_returns_400(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "approve",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_accept_without_true_dob_returns_400(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "accept",
        })
        assert resp.status_code == 400

    def test_accept_high_candidate_flags_ie_record_for_correction(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "accept",
            "true_dob": "1980-04-03", "reviewer": "reviewer@doane.edu",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["correctedPersonId"] == "1001"
        assert data["correctedFrom"] == "1980-04-02"
        assert data["correctedTo"] == "1980-04-03"

    def test_accept_true_dob_must_match_a_side(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "accept",
            "true_dob": "1999-01-01",
        })
        assert resp.status_code == 400

    def test_reject_records_no_correction(self, client):
        _upload(client)
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": LEE_REVIEW, "action": "reject", "reviewer": "r",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["correctedPersonId"] is None

    def test_decision_persists_across_candidate_reload(self, client):
        _upload(client)
        client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "accept", "true_dob": "1980-04-03",
        })
        resp = client.get("/api/v1/dob-repair/candidates")
        smith = next(c for c in resp.get_json()["candidates"] if c["candidate_id"] == SMITH_HIGH)
        assert smith["decision"]["action"] == "accept"
        assert smith["decision"]["correctedPersonId"] == "1001"

    def test_decision_upserts_on_resubmit(self, client):
        _upload(client)
        client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": LEE_REVIEW, "action": "defer",
        })
        resp = client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": LEE_REVIEW, "action": "reject", "note": "typo, not the bug",
        })
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "reject"


class TestExportCorrections:
    def test_export_is_csv(self, client):
        _upload(client)
        resp = client.get("/api/v1/dob-repair/export/corrections")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_export_contains_only_accepted_with_correction(self, client):
        _upload(client)
        client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": SMITH_HIGH, "action": "accept", "true_dob": "1980-04-03",
        })
        client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": KING_HIGH, "action": "defer",
        })
        client.post("/api/v1/dob-repair/decision", json={
            "candidate_id": LEE_REVIEW, "action": "reject",
        })

        resp = client.get("/api/v1/dob-repair/export/corrections")
        csv_text = resp.data.decode("utf-8")
        assert "person_id,current_dob,corrected_dob" in csv_text
        assert "1001,1980-04-02,1980-04-03" in csv_text
        # Deferred/rejected decisions never appear in the export.
        assert "3001" not in csv_text
        assert "5001" not in csv_text
        assert "5002" not in csv_text

    def test_export_empty_before_any_acceptance(self, client):
        _upload(client)
        resp = client.get("/api/v1/dob-repair/export/corrections")
        csv_text = resp.data.decode("utf-8")
        lines = [l for l in csv_text.strip().splitlines() if l]
        assert len(lines) == 1  # header only
