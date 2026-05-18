"""Entry point for the Conductor Companion Flask application."""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug, use_reloader=False)
