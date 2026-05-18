"""SavedSearch model."""
from datetime import datetime

from app import db


class SavedSearch(db.Model):
    """Persisted search configuration that users can recall by name."""

    __tablename__ = "saved_searches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, default="")
    search_config = db.Column(db.JSON, nullable=False, default=dict)
    created_by = db.Column(db.String(100), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    use_count = db.Column(db.Integer, default=0, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "searchConfig": self.search_config,
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
            "useCount": self.use_count,
        }
