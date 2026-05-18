"""Flask application factory for Conductor Companion."""
import logging
import os
import sys
import time

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

_start_time = time.time()


def create_app(config_override=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Configure database
    database_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
    app.config["SERVICE_VERSION"] = os.environ.get("SERVICE_VERSION", "1.0.0")
    app.config["START_TIME"] = _start_time

    if config_override:
        app.config.update(config_override)

    # Configure structured JSON logging to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from app.routes.health import health_bp
    from app.routes.search import search_bp
    from app.routes.jq_lab import jq_lab_bp
    from app.routes.workers import workers_bp
    from app.routes.batches import batches_bp
    from app.routes.diff import diff_bp
    from app.routes.secrets import secrets_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(jq_lab_bp)
    app.register_blueprint(workers_bp)
    app.register_blueprint(batches_bp)
    app.register_blueprint(diff_bp)
    app.register_blueprint(secrets_bp)

    # Register main UI route
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Create tables if using sqlite (dev/test) or if DB available
    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:
            app.logger.warning("Could not create database tables: %s", exc)

    return app


class StructuredFormatter(logging.Formatter):
    """Emit structured JSON log records to stdout."""

    def format(self, record):
        import json
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)
