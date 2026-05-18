"""Routes package — exposes main UI blueprint."""
from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Serve the single-page application shell."""
    return render_template("index.html")
