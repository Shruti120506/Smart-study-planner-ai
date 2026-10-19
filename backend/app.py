"""
Smart Study Planner AI - Flask Backend
Phase 2: SQLite Database Initialization & REST API Endpoints
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path so running `python backend/app.py` works out of the box
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify
from flask_cors import CORS

from backend.database.db import init_db, close_db_connection, get_db_connection
from backend.routes.subjects_bp import subjects_bp
from backend.routes.preferences_bp import preferences_bp


def create_app(test_config=None):
    """
    Application factory for the Flask app.
    Initializes database schema and registers API blueprints.
    """
    app = Flask(__name__)

    # Default configuration
    default_db = PROJECT_ROOT / "instance" / "planner.db"
    app.config.from_mapping(
        DATABASE=str(default_db),
        JSON_SORT_KEYS=False
    )

    # Override config if test_config is provided (e.g., during pytest execution)
    if test_config:
        app.config.update(test_config)

    # Enable Cross-Origin Resource Sharing (CORS) for local development
    CORS(app)

    # Register teardown function to close SQLite connections after requests
    app.teardown_appcontext(close_db_connection)

    # Initialize database tables and default data on app startup
    with app.app_context():
        init_db(app)

    # Register Blueprints
    app.register_blueprint(subjects_bp)
    app.register_blueprint(preferences_bp)

    @app.route("/")
    def index():
        """Root welcome endpoint with API discovery."""
        return jsonify({
            "message": "Welcome to Smart Study Planner AI API",
            "status": "online",
            "version": "1.1.0",
            "phase": "Phase 2 - SQLite Database and Persistence Active",
            "endpoints": {
                "health": "/api/health",
                "subjects": "/api/subjects",
                "sample_subjects": "POST /api/subjects/sample",
                "preferences": "/api/preferences"
            }
        }), 200

    @app.route("/api/health")
    def health_check():
        """Health check endpoint to verify backend server and database status."""
        db_status = "unknown"
        try:
            conn = get_db_connection()
            conn.execute("SELECT 1").fetchone()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"

        return jsonify({
            "status": "healthy" if db_status == "connected" else "degraded",
            "service": "Smart Study Planner AI Backend",
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_status": "ok"
        }), 200

    return app


app = create_app()

if __name__ == "__main__":
    # Runs local dev server on http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)
