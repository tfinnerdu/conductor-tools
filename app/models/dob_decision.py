"""DobDecision model.

Human review decisions for DOB Repair (PD0002124) candidates. The detector
(app/dob_detector.py) proposes; this table is where a reviewer disposes.
Nothing here writes to Colleague — a decision only marks which record a human
has approved for correction. The actual write happens outside Conductor
Companion, through a sanctioned Ethos/NAE channel, using the CSV this table
feeds via GET /api/v1/dob-repair/export/corrections.

candidate_id is the detector's stable, order-independent pair key
(sorted person_id pair), so decisions survive re-analysis against a fresh
PERSON export as long as the same two person_ids reappear.
"""
from datetime import datetime

from app import db

VALID_DECISIONS = {"accept", "reject", "defer"}


class DobDecision(db.Model):
    """Reviewer disposition for one DOB Repair candidate pair."""

    __tablename__ = "dob_decisions"

    candidate_id = db.Column(db.String(200), primary_key=True)
    action = db.Column(db.String(20), nullable=False)
    corrected_person_id = db.Column(db.String(100))
    corrected_from = db.Column(db.String(20))
    corrected_to = db.Column(db.String(20))
    reviewer = db.Column(db.String(100), default="unknown")
    decided_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    note = db.Column(db.Text, default="")

    def to_dict(self) -> dict:
        return {
            "candidateId": self.candidate_id,
            "action": self.action,
            "correctedPersonId": self.corrected_person_id,
            "correctedFrom": self.corrected_from,
            "correctedTo": self.corrected_to,
            "reviewer": self.reviewer,
            "decidedAt": self.decided_at.isoformat() + "Z" if self.decided_at else None,
            "note": self.note or "",
        }
