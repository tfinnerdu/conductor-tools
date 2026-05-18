"""TestPreset model — stores custom workflow test presets."""
from datetime import datetime

from app import db


class TestPreset(db.Model):
    """A saved test preset with workflow input and task mock data."""

    __tablename__ = "test_presets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    workflow_name = db.Column(db.String(200), default="")
    input_data = db.Column(db.JSON, nullable=False, default=dict)
    task_mocks = db.Column(db.JSON, nullable=False, default=dict)
    created_by = db.Column(db.String(100), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "workflowName": self.workflow_name,
            "input": self.input_data,
            "taskMocks": self.task_mocks,
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
