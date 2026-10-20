"""
Authentication Blueprint for Smart Study Planner AI
Provides endpoints for registration, login, logout, session status, and CSRF token.
"""

from flask import Blueprint, jsonify, request, session, current_app
from datetime import timedelta

try:
    from backend.database.db import get_db_connection
    from backend.auth.security import (
        hash_password,
        verify_password,
        generate_csrf_token,
        get_current_user,
        validate_registration_payload
    )
except ImportError:
    from database.db import get_db_connection
    from auth.security import (
        hash_password,
        verify_password,
        generate_csrf_token,
        get_current_user,
        validate_registration_payload
    )

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/csrf", methods=["GET"])
def get_csrf():
    """Retrieve or generate CSRF token for the session."""
    token = generate_csrf_token()
    return jsonify({
        "success": True,
        "csrf_token": token
    }), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new student user."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "messages": ["Request body must be a valid JSON object with Content-Type: application/json."]
            }
        }), 400

    is_valid, errors, cleaned = validate_registration_payload(data)
    if not is_valid:
        return jsonify({
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "messages": errors
            }
        }), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check for existing email (case-insensitive)
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (cleaned["email"],))
    existing = cursor.fetchone()
    if existing:
        return jsonify({
            "success": False,
            "error": {
                "code": "DUPLICATE_EMAIL",
                "messages": ["An account with this email address already exists. Please log in."]
            }
        }), 409

    pwd_hash = hash_password(cleaned["password"])
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (cleaned["name"], cleaned["email"], pwd_hash)
    )
    user_id = cursor.lastrowid

    # Initialize default study preferences for the new user
    cursor.execute(
        """
        INSERT INTO study_preferences (user_id, daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, 4.0, "morning", 45, "medium")
    )
    conn.commit()

    # Establish authenticated session
    session.clear()
    session["user_id"] = user_id
    generate_csrf_token()

    return jsonify({
        "success": True,
        "message": "Registration successful! Welcome to Smart Study Planner AI.",
        "user": {
            "id": user_id,
            "name": cleaned["name"],
            "email": cleaned["email"]
        }
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate student user and create session."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "messages": ["Request body must be a valid JSON object."]
            }
        }), 400

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    remember_me = bool(data.get("remember_me", False))

    if not email or not password:
        return jsonify({
            "success": False,
            "error": {
                "code": "MISSING_CREDENTIALS",
                "messages": ["Please provide both email and password."]
            }
        }), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    user_row = cursor.fetchone()

    if not user_row or not verify_password(password, user_row["password_hash"]):
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_CREDENTIALS",
                "messages": ["Invalid email or password. Please try again."]
            }
        }), 401

    # Establish session
    session.clear()
    session["user_id"] = user_row["id"]
    if remember_me:
        session.permanent = True
        current_app.permanent_session_lifetime = timedelta(days=30)
    else:
        session.permanent = False

    generate_csrf_token()

    return jsonify({
        "success": True,
        "message": "Login successful. Welcome back!",
        "user": {
            "id": user_row["id"],
            "name": user_row["name"],
            "email": user_row["email"]
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Clear session and log out the user."""
    session.clear()
    return jsonify({
        "success": True,
        "message": "You have been logged out successfully."
    }), 200


@auth_bp.route("/me", methods=["GET"])
def get_me():
    """Check current authenticated session and return user profile."""
    user = get_current_user()
    if not user:
        return jsonify({
            "success": False,
            "authenticated": False,
            "user": None
        }), 200

    return jsonify({
        "success": True,
        "authenticated": True,
        "user": user
    }), 200
