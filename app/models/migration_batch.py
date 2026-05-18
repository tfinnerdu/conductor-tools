"""MigrationBatch model."""
from datetime import datetime

from app import db


class MigrationBatch(db.Model):
    """Tracks a batch migration job driven by Conductor workflow executions."""

    __tablename__ = "migration_batches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    workflow_name = db.Column(db.String(200), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    correlation_id_prefix = db.Column(db.String(200), default="")
    total_expected = db.Column(db.Integer, default=0)
    created_by = db.Column(db.String(100), default="user")
    notes = db.Column(db.Text, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "workflowName": self.workflow_name,
            "startedAt": self.started_at.isoformat() + "Z" if self.started_at else None,
            "correlationIdPrefix": self.correlation_id_prefix,
            "totalExpected": self.total_expected,
            "createdBy": self.created_by,
            "notes": self.notes,
        }
