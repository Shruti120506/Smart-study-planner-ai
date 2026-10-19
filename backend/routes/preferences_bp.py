"""
Preferences Blueprint for Smart Study Planner AI
Provides endpoints to view and update daily study hours, fatigue, and focus span.
"""

from flask import Blueprint, jsonify, request
try:
    from backend.database.db import get_db_connection
    from backend.routes.validators import validate_preferences_payload
except ImportError:
    from database.db import get_db_connection
    from routes.validators import validate_preferences_payload

preferences_bp = Blueprint("preferences", __name__, url_prefix="/api/preferences")


def get_or_create_preferences(conn):
    """Fetches the latest student preferences record or inserts default values."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM study_preferences ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            """
            INSERT INTO study_preferences 
            (daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level)
            VALUES (?, ?, ?, ?)
            """,
            (4.0, "morning", 45, "medium")
        )
        conn.commit()
        cursor.execute("SELECT * FROM study_preferences ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()

    return dict(row)


@preferences_bp.route("", methods=["GET"])
def get_preferences():
    """Retrieve current student study preferences."""
    conn = get_db_connection()
    prefs = get_or_create_preferences(conn)

    return jsonify({
        "success": True,
        "preferences": prefs
    }), 200


@preferences_bp.route("", methods=["PUT", "POST"])
def update_preferences():
    """Update current student study preferences."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "messages": ["Request body must be a valid JSON object with Content-Type: application/json."]
            }
        }), 400

    is_valid, errors, cleaned = validate_preferences_payload(data)

    if not is_valid:
        return jsonify({
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "messages": errors
            }
        }), 400

    conn = get_db_connection()
    current = get_or_create_preferences(conn)
    cursor = conn.cursor()

    fields_to_update = []
    params = []
    for field in ["daily_available_hours", "preferred_time_of_day", "focus_span_minutes", "fatigue_level"]:
        if field in cleaned:
            fields_to_update.append(f"{field} = ?")
            params.append(cleaned[field])

    if not fields_to_update:
        return jsonify({
            "success": False,
            "error": {
                "code": "NO_FIELDS_PROVIDED",
                "messages": [
                    "No valid preference fields provided for update. "
                    "Allowed: daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level."
                ]
            }
        }), 400

    fields_to_update.append("updated_at = CURRENT_TIMESTAMP")
    params.append(current["id"])
    query = f"UPDATE study_preferences SET {', '.join(fields_to_update)} WHERE id = ?"
    cursor.execute(query, tuple(params))
    conn.commit()

    updated = get_or_create_preferences(conn)

    return jsonify({
        "success": True,
        "message": "Study preferences updated successfully.",
        "preferences": updated
    }), 200
