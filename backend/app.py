"""
Smart Study Planner AI - Flask Backend
Phase 1: Basic Server Setup & Health Check
"""

from datetime import datetime, timezone
from flask import Flask, jsonify
from flask_cors import CORS

def create_app():
    """Application factory for the Flask app."""
    app = Flask(__name__)

    # Enable Cross-Origin Resource Sharing (CORS) for local development
    CORS(app)

    @app.route("/")
    def index():
        """Root welcome endpoint."""
        return jsonify({
            "message": "Welcome to Smart Study Planner AI API",
            "status": "online",
            "version": "1.0.0",
            "endpoints": {
                "health": "/api/health",
                "docs": "Phase 1 - Server initialized successfully"
            }
        }), 200

    @app.route("/api/health")
    def health_check():
        """Health check endpoint to verify backend server status."""
        return jsonify({
            "status": "healthy",
            "service": "Smart Study Planner AI Backend",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_status": "ok"
        }), 200

    return app


app = create_app()

if __name__ == "__main__":
    # Runs local dev server on http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)
