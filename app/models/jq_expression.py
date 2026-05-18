"""JqExpression model."""
from datetime import datetime

from app import db


class JqExpression(db.Model):
    """A saved jq expression in the expression library."""

    __tablename__ = "jq_expressions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, default="")
    expression = db.Column(db.Text, nullable=False)
    resource_name = db.Column(db.String(200), default="")
    use_case = db.Column(db.String(200), default="")
    created_by = db.Column(db.String(100), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    use_count = db.Column(db.Integer, default=0, nullable=False)
    tags = db.Column(db.String(500), default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "expression": self.expression,
            "resourceName": self.resource_name,
            "useCase": self.use_case,
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
            "useCount": self.use_count,
            "tags": self.tags,
        }
