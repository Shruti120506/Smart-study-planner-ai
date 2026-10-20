"""
Subjects Blueprint for Smart Study Planner AI
Provides REST endpoints for Subject CRUD and sample data population, scoped to authenticated user.
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
try:
    from backend.database.db import get_db_connection, load_sample_subjects
    from backend.routes.validators import validate_subject_payload
    from backend.auth.security import login_required_api, get_current_user_id
except ImportError:
    from database.db import get_db_connection, load_sample_subjects
    from routes.validators import validate_subject_payload
    from auth.security import login_required_api, get_current_user_id

subjects_bp = Blueprint("subjects", __name__, url_prefix="/api/subjects")


def enrich_subject_row(row):
    """Adds calculated fields (progress %, remaining units, days to exam) to subject record."""
    item = dict(row)
    total = item["syllabus_units_total"]
    completed = item["units_completed"]

    item["completion_percentage"] = round((completed / total) * 100, 1) if total > 0 else 0.0
    item["remaining_units"] = max(0, total - completed)

    if item.get("exam_date"):
        try:
            exam_dt = datetime.strptime(item["exam_date"], "%Y-%m-%d").date()
            today = datetime.now().date()
            item["days_until_exam"] = (exam_dt - today).days
        except ValueError:
            item["days_until_exam"] = None
    else:
        item["days_until_exam"] = None

    return item


@subjects_bp.route("", methods=["GET"], strict_slashes=False)
@login_required_api
def list_subjects():
    """Retrieve all enrolled subjects for the active user sorted by exam date and creation time."""
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute(
            """
            SELECT * FROM subjects 
            WHERE user_id = ?
            ORDER BY 
                CASE WHEN exam_date IS NULL THEN 1 ELSE 0 END,
                exam_date ASC, 
                id ASC
            """,
            (user_id,)
        )
    else:
        cursor.execute(
            """
            SELECT * FROM subjects 
            WHERE user_id IS NULL
            ORDER BY 
                CASE WHEN exam_date IS NULL THEN 1 ELSE 0 END,
                exam_date ASC, 
                id ASC
            """
        )
    rows = cursor.fetchall()
    subjects = [enrich_subject_row(r) for r in rows]

    return jsonify({
        "success": True,
        "count": len(subjects),
        "subjects": subjects
    }), 200


@subjects_bp.route("/<int:subject_id>", methods=["GET"])
@login_required_api
def get_subject(subject_id):
    """Retrieve a single subject by ID (scoped to active user)."""
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id))
    else:
        cursor.execute("SELECT * FROM subjects WHERE id = ? AND user_id IS NULL", (subject_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Subject with ID {subject_id} was not found."
            }
        }), 404

    return jsonify({
        "success": True,
        "subject": enrich_subject_row(row)
    }), 200


@subjects_bp.route("", methods=["POST"], strict_slashes=False)
@login_required_api
def create_subject():
    """Create a new academic subject for the active user."""
    user_id = get_current_user_id()
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "messages": ["Request body must be a valid JSON object with Content-Type: application/json."]
            }
        }), 400

    is_valid, errors, cleaned = validate_subject_payload(data, is_update=False)

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

    # Check for duplicate subject name scoped to active user
    if user_id is not None:
        cursor.execute("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND user_id = ?", (cleaned["name"], user_id))
    else:
        cursor.execute("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND user_id IS NULL", (cleaned["name"],))

    if cursor.fetchone():
        return jsonify({
            "success": False,
            "error": {
                "code": "DUPLICATE_SUBJECT",
                "message": f"A subject named '{cleaned['name']}' already exists."
            }
        }), 409

    cursor.execute(
        """
        INSERT INTO subjects (user_id, name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            cleaned["name"],
            cleaned.get("difficulty_level", "medium"),
            cleaned.get("target_grade", "A"),
            cleaned.get("exam_date"),
            cleaned.get("syllabus_units_total", 5),
            cleaned.get("units_completed", 0)
        )
    )
    conn.commit()
    new_id = cursor.lastrowid

    cursor.execute("SELECT * FROM subjects WHERE id = ?", (new_id,))
    created_row = cursor.fetchone()

    return jsonify({
        "success": True,
        "message": "Subject created successfully.",
        "subject": enrich_subject_row(created_row)
    }), 201


@subjects_bp.route("/<int:subject_id>", methods=["PUT"])
@login_required_api
def update_subject(subject_id):
    """Update an existing subject by ID (scoped to active user)."""
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id))
    else:
        cursor.execute("SELECT * FROM subjects WHERE id = ? AND user_id IS NULL", (subject_id,))
    existing = cursor.fetchone()

    if not existing:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Subject with ID {subject_id} was not found."
            }
        }), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "error": {
                "code": "INVALID_JSON",
                "messages": ["Request body must be a valid JSON object with Content-Type: application/json."]
            }
        }), 400

    is_valid, errors, cleaned = validate_subject_payload(data, is_update=True, existing_subject=existing)

    if not is_valid:
        return jsonify({
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "messages": errors
            }
        }), 400

    # If updating name, check it doesn't conflict with another existing subject belonging to same user
    if "name" in cleaned and cleaned["name"].lower() != existing["name"].lower():
        if user_id is not None:
            cursor.execute(
                "SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND id != ? AND user_id = ?",
                (cleaned["name"], subject_id, user_id)
            )
        else:
            cursor.execute(
                "SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND id != ? AND user_id IS NULL",
                (cleaned["name"], subject_id)
            )
        if cursor.fetchone():
            return jsonify({
                "success": False,
                "error": {
                    "code": "DUPLICATE_SUBJECT",
                    "message": f"Another subject named '{cleaned['name']}' already exists."
                }
            }), 409

    fields_to_update = []
    params = []
    for field in ["name", "difficulty_level", "target_grade", "exam_date", "syllabus_units_total", "units_completed"]:
        if field in cleaned:
            fields_to_update.append(f"{field} = ?")
            params.append(cleaned[field])

    if not fields_to_update:
        return jsonify({
            "success": True,
            "message": "No changes requested.",
            "subject": enrich_subject_row(existing)
        }), 200

    fields_to_update.append("updated_at = CURRENT_TIMESTAMP")
    params.append(subject_id)

    query = f"UPDATE subjects SET {', '.join(fields_to_update)} WHERE id = ?"
    cursor.execute(query, tuple(params))
    conn.commit()

    cursor.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,))
    updated_row = cursor.fetchone()

    return jsonify({
        "success": True,
        "message": "Subject updated successfully.",
        "subject": enrich_subject_row(updated_row)
    }), 200


@subjects_bp.route("/<int:subject_id>", methods=["DELETE"])
@login_required_api
def delete_subject(subject_id):
    """Delete a subject by ID (scoped to active user)."""
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute("SELECT name FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id))
    else:
        cursor.execute("SELECT name FROM subjects WHERE id = ? AND user_id IS NULL", (subject_id,))
    existing = cursor.fetchone()

    if not existing:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Subject with ID {subject_id} was not found."
            }
        }), 404

    cursor.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()

    return jsonify({
        "success": True,
        "message": f"Subject '{existing['name']}' deleted successfully."
    }), 200


@subjects_bp.route("/sample", methods=["POST"])
@login_required_api
def seed_sample_subjects():
    """Load pre-configured sample college subjects for active user without creating duplicates."""
    user_id = get_current_user_id()
    result = load_sample_subjects(user_id=user_id)
    return jsonify({
        "success": True,
        "message": f"Sample subjects loaded: {result['added_count']} added, {result['skipped_count']} already present.",
        "details": result
    }), 200
