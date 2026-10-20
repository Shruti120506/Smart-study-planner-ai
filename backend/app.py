"""
Smart Study Planner AI - Flask Backend
Phase 4: Rule-Based AI Engine, Multi-Tenant Authentication & Productivity UI
Robust import configuration supporting execution from any directory.
"""

import os
import sys
import secrets
from datetime import datetime, timezone
from pathlib import Path

# Resolve directory paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Add both PROJECT_ROOT and BACKEND_DIR to sys.path so imports work regardless of working directory
for path_str in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from flask import Flask, jsonify, send_from_directory, request, redirect
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Dual import support (works whether imported as backend.X or X)
try:
    from backend.database.db import init_db, close_db_connection, get_db_connection
    from backend.routes.subjects_bp import subjects_bp
    from backend.routes.preferences_bp import preferences_bp
    from backend.routes.ai_bp import ai_bp
    from backend.routes.auth_bp import auth_bp
    from backend.auth.security import get_current_user, login_required_web
except ImportError:
    from database.db import init_db, close_db_connection, get_db_connection
    from routes.subjects_bp import subjects_bp
    from routes.preferences_bp import preferences_bp
    from routes.ai_bp import ai_bp
    from routes.auth_bp import auth_bp
    from auth.security import get_current_user, login_required_web


def create_app(test_config=None):
    """
    Application factory for the Flask app.
    Initializes database schema and registers API blueprints.
    """
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="/static"
    )

    # Environment detection
    flask_env = os.environ.get("FLASK_ENV", "development").lower()
    is_render = "RENDER" in os.environ
    is_prod = flask_env == "production" or is_render

    # Default configuration: instance/planner.db in project root
    default_db = PROJECT_ROOT / "instance" / "planner.db"
    database_url = os.environ.get("DATABASE_URL")

    # SECRET_KEY resolution: In production, require an explicit, non-default SECRET_KEY
    hardcoded_default_key = "smart-study-planner-secret-key-production-ready-2026"
    env_secret_key = os.environ.get("SECRET_KEY")

    if is_prod and not (test_config and test_config.get("TESTING")):
        if not env_secret_key or env_secret_key == hardcoded_default_key or len(env_secret_key) < 32:
            raise RuntimeError(
                "CRITICAL PRODUCTION SECURITY ERROR: A secure, random SECRET_KEY environment variable "
                "(minimum 32 characters) must be configured in production/Render. Do not use default keys."
            )
        secret_key = env_secret_key
    else:
        # Development / local fallback
        secret_key = env_secret_key or hardcoded_default_key

    # Configure secure cookies in production/Render
    cookie_secure = is_prod

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DATABASE=str(default_db),
        DATABASE_URL=database_url,
        JSON_SORT_KEYS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cookie_secure,
        LEGACY_TEST_MODE=True
    )

    # Apply ProxyFix middleware behind Render's reverse proxy so request.is_secure and headers are trusted
    if is_prod:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Override config if test_config is provided (e.g., during pytest execution)
    if test_config:
        app.config.update(test_config)

    # Enable Cross-Origin Resource Sharing (CORS) for local development
    CORS(app, supports_credentials=True)

    # Register teardown function to close SQLite connections after requests
    app.teardown_appcontext(close_db_connection)

    # Initialize database tables and default data on app startup
    with app.app_context():
        init_db(app)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(preferences_bp)
    app.register_blueprint(ai_bp)

    @app.route("/")
    def index():
        """Root welcome endpoint with API discovery and browser redirection."""
        # If accessed via web browser expecting HTML:
        if request.accept_mimetypes.accept_html and not request.accept_mimetypes.accept_json:
            user = get_current_user()
            if not user and not (app.config.get("TESTING") and app.config.get("LEGACY_TEST_MODE", True)):
                return redirect("/login")
            index_file = FRONTEND_DIR / "index.html"
            if index_file.exists():
                return send_from_directory(FRONTEND_DIR, "index.html")

        return jsonify({
            "message": "Welcome to Smart Study Planner AI API",
            "status": "online",
            "version": "3.0.0",
            "phase": "Phase 6 - User Authentication & Modern Dashboard Active",
            "dashboard_url": "/dashboard",
            "endpoints": {
                "health": "/api/health",
                "auth_register": "POST /api/auth/register",
                "auth_login": "POST /api/auth/login",
                "auth_logout": "POST /api/auth/logout",
                "auth_me": "GET /api/auth/me",
                "subjects": "/api/subjects",
                "sample_subjects": "POST /api/subjects/sample",
                "preferences": "/api/preferences",
                "ai_plan": "POST /api/ai/plan",
                "ai_plan_latest": "GET /api/ai/plan/latest",
                "ai_plan_by_id": "GET /api/ai/plan/<plan_id>",
                "ai_complete_item": "PATCH /api/ai/plan/items/<item_id>/complete",
                "ai_goals": "POST /api/ai/goals",
                "ai_rules": "GET /api/ai/rules",
                "ai_explain": "GET /api/ai/explain/<plan_id>"
            }
        }), 200

    @app.route("/login")
    def login_page():
        """Serve the Student Login Page UI."""
        user = get_current_user()
        if user:
            return redirect("/dashboard")
        login_file = FRONTEND_DIR / "login.html"
        if not login_file.exists():
            return jsonify({"error": "Login UI template not found."}), 404
        return send_from_directory(FRONTEND_DIR, "login.html")

    @app.route("/register")
    def register_page():
        """Serve the Student Registration Page UI."""
        user = get_current_user()
        if user:
            return redirect("/dashboard")
        register_file = FRONTEND_DIR / "register.html"
        if not register_file.exists():
            return jsonify({"error": "Registration UI template not found."}), 404
        return send_from_directory(FRONTEND_DIR, "register.html")

    @app.route("/dashboard")
    @login_required_web
    def dashboard():
        """Serve the Student Dashboard UI."""
        index_file = FRONTEND_DIR / "index.html"
        if not index_file.exists():
            return jsonify({
                "error": "Frontend dashboard not found. Ensure frontend/index.html exists."
            }), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

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

    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": {
                    "code": "BAD_REQUEST",
                    "message": str(e.description) if hasattr(e, "description") else "Bad request."
                }
            }), 400
        return e

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/") or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
            return jsonify({
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Endpoint '{request.path}' was not found on this server."
                }
            }), 404
        return e

    @app.errorhandler(405)
    def method_not_allowed(e):
        if request.path.startswith("/api/") or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
            return jsonify({
                "success": False,
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": f"HTTP method {request.method} is not allowed for '{request.path}'."
                }
            }), 405
        return e

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred."
                }
            }), 500
        return e

    return app


app = create_app()

if __name__ == "__main__":
    # Runs local dev server on http://127.0.0.1:5000 or custom PORT
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.environ.get("FLASK_ENV", "development").lower() != "production" and "RENDER" not in os.environ
    app.run(host="0.0.0.0", port=port, debug=is_debug)
