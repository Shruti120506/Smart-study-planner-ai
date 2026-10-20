"""
Smart Study Planner AI – AI Blueprint (Phase 3)
Flask routes that expose the rule-based AI engine via REST endpoints, scoped to authenticated user.

Endpoints:
  POST /api/ai/plan        – Generate today's study plan (forward chaining)
  POST /api/ai/goals       – Analyse goal feasibility (backward chaining)
  GET  /api/ai/rules       – List all IF-THEN rules in the knowledge base
  GET  /api/ai/explain/<plan_id> – Retrieve logged rule explanations for a plan
"""

from datetime import datetime, date
from flask import Blueprint, jsonify, request, current_app

try:
    from backend.database.db import get_db_connection
    from backend.ai.knowledge_base import get_rules, get_rule_by_id
    from backend.ai.working_memory import WorkingMemory
    from backend.ai.forward_chainer import ForwardChainer
    from backend.ai.backward_chainer import BackwardChainer
    from backend.ai.explanation_generator import ExplanationGenerator
    from backend.auth.security import login_required_api, get_current_user_id
except ImportError:
    from database.db import get_db_connection
    from ai.knowledge_base import get_rules, get_rule_by_id
    from ai.working_memory import WorkingMemory
    from ai.forward_chainer import ForwardChainer
    from ai.backward_chainer import BackwardChainer
    from ai.explanation_generator import ExplanationGenerator
    from auth.security import login_required_api, get_current_user_id

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_subjects_and_prefs(conn, user_id=None):
    """Load subjects and study preferences from the database for user_id."""
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute(
            """
            SELECT * FROM subjects
            WHERE user_id = ?
            ORDER BY
                CASE WHEN exam_date IS NULL THEN 1 ELSE 0 END,
                exam_date ASC, id ASC
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
                exam_date ASC, id ASC
            """
        )
    subjects = [dict(row) for row in cursor.fetchall()]

    if user_id is not None:
        cursor.execute("SELECT * FROM study_preferences WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    else:
        cursor.execute("SELECT * FROM study_preferences WHERE user_id IS NULL ORDER BY id DESC LIMIT 1")
    prefs_row = cursor.fetchone()
    preferences = dict(prefs_row) if prefs_row else {
        "daily_available_hours": 4.0,
        "preferred_time_of_day": "morning",
        "focus_span_minutes": 45,
        "fatigue_level": "medium",
    }

    return subjects, preferences


def _save_plan(conn, plan_date: str, plan_result: dict, user_id=None) -> int:
    """
    Persist the generated plan and its items to the database.
    Returns the new plan_id.
    """
    cursor = conn.cursor()

    total_allocated = sum(
        item.get("allocated_minutes", 0)
        for item in plan_result.get("plan_items", [])
    )
    total_hours = round(total_allocated / 60.0, 2)

    cursor.execute(
        """
        INSERT INTO study_plans (user_id, plan_date, total_hours_allocated, strategy_used)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, plan_date, total_hours, "forward_chaining_rule_based")
    )
    plan_id = cursor.lastrowid

    for item in plan_result.get("plan_items", []):
        cursor.execute(
            """
            INSERT INTO plan_items
            (plan_id, subject_id, session_title, allocated_minutes,
             break_minutes, priority, session_type,
             recommended_time_slot, fired_rule_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                item["subject_id"],
                item["session_title"],
                item["allocated_minutes"],
                item.get("break_minutes", 10),
                item["priority"],
                item["session_type"],
                item.get("recommended_time_slot", "morning"),
                item.get("fired_rule_id", ""),
            )
        )
        item["id"] = cursor.lastrowid
        item["is_completed"] = 0

    # Log each fired rule into rule_logs for transparency
    for expl in plan_result.get("explanations", []):
        conditions_str = "; ".join(expl.get("conditions_matched", []))
        action = expl.get("action_taken", {})
        cursor.execute(
            """
            INSERT INTO rule_logs
            (plan_id, rule_id, rule_name, condition_matched, action_taken)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                expl["rule_id"],
                expl["rule_name"],
                conditions_str,
                action.get("session_label", ""),
            )
        )

    conn.commit()
    return plan_id


def _fetch_plan_with_items(conn, plan_id: int, user_id=None):
    """Fetch study plan and its plan items with subject details, verifying user_id ownership."""
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT * FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
    else:
        cursor.execute("SELECT * FROM study_plans WHERE id = ? AND user_id IS NULL", (plan_id,))
    plan_row = cursor.fetchone()
    if not plan_row:
        return None

    plan = dict(plan_row)

    cursor.execute(
        """
        SELECT 
            pi.*,
            s.name AS subject_name,
            s.difficulty_level,
            s.exam_date,
            s.target_grade,
            s.syllabus_units_total,
            s.units_completed
        FROM plan_items pi
        LEFT JOIN subjects s ON s.id = pi.subject_id
        WHERE pi.plan_id = ?
        ORDER BY pi.id ASC
        """,
        (plan_id,)
    )
    items = [dict(row) for row in cursor.fetchall()]

    completed_count = sum(1 for item in items if item.get("is_completed") == 1)
    planned_minutes = sum(item.get("allocated_minutes", 0) for item in items)
    completed_minutes = sum(item.get("allocated_minutes", 0) for item in items if item.get("is_completed") == 1)

    plan["plan_items"] = items
    plan["total_sessions"] = len(items)
    plan["completed_sessions"] = completed_count
    plan["planned_minutes"] = planned_minutes
    plan["completed_minutes"] = completed_minutes
    plan["planned_hours"] = round(planned_minutes / 60.0, 2)
    plan["completed_hours"] = round(completed_minutes / 60.0, 2)
    plan["completion_percentage"] = (
        round((completed_count / len(items)) * 100, 1) if items else 0.0
    )

    return plan


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@ai_bp.route("/plan", methods=["POST"])
@login_required_api
def generate_plan():
    """
    Generate a daily study plan using forward chaining for the active user.

    Optional JSON body:
      { "save": true }   – save plan to DB (default: true)
    """
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    should_save = body.get("save", True)

    conn = get_db_connection()
    subjects, preferences = _fetch_subjects_and_prefs(conn, user_id=user_id)

    if not subjects:
        return jsonify({
            "success": True,
            "message": "No subjects found. Add subjects first via POST /api/subjects.",
            "plan_items": [],
            "plan_summary": {
                "urgency_note": "No subjects to plan for.",
                "total_subjects_planned": 0,
            },
            "explanations": [],
        }), 200

    # Run forward chaining
    wm = WorkingMemory(subjects, preferences)
    fc = ForwardChainer()
    plan_result = fc.generate_plan(wm)

    plan_id = None
    if should_save and plan_result["plan_items"]:
        plan_date = date.today().isoformat()
        plan_id = _save_plan(conn, plan_date, plan_result, user_id=user_id)

    return jsonify({
        "success": True,
        "message": "Study plan generated successfully using forward chaining.",
        "plan_id": plan_id,
        "plan_items": plan_result["plan_items"],
        "plan_summary": plan_result["plan_summary"],
        "explanations": plan_result["explanations"],
        "working_memory_summary": plan_result["summary"],
    }), 200


@ai_bp.route("/goals", methods=["POST"])
@login_required_api
def analyse_goals():
    """
    Analyse study goal feasibility using backward chaining for the active user.

    Optional JSON body:
      { "subject_id": 3 }  – analyse a single subject (omit for all)
    """
    user_id = get_current_user_id()
    body = request.get_json(silent=True) or {}
    target_subject_id = body.get("subject_id")

    conn = get_db_connection()
    subjects, preferences = _fetch_subjects_and_prefs(conn, user_id=user_id)

    # If a specific subject_id was requested, filter first (404 if not found)
    if target_subject_id is not None:
        subjects = [s for s in subjects if s.get("id") == target_subject_id]
        if not subjects:
            return jsonify({
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Subject with ID {target_subject_id} was not found."
                }
            }), 404

    if not subjects:
        return jsonify({
            "success": True,
            "message": "No subjects found.",
            "goal_results": [],
            "overall_feasible": True,
            "overall_explanation": "No subjects to analyse.",
        }), 200

    # Also run forward chaining to get priorities for budget share
    wm_fc = WorkingMemory(subjects, preferences)
    fc = ForwardChainer()
    forward_result = fc.generate_plan(wm_fc)

    # Now run backward chaining
    wm_bc = WorkingMemory(subjects, preferences)
    bc = BackwardChainer()
    goal_result = bc.check_goals(wm_bc, forward_plan=forward_result["plan_items"])

    return jsonify({
        "success": True,
        "message": "Goal feasibility analysis complete (backward chaining).",
        **goal_result,
    }), 200


@ai_bp.route("/rules", methods=["GET"])
def list_rules():
    """
    Return all IF-THEN rules in the knowledge base (human-readable).
    Useful for the viva: shows what rules the AI knows. Public endpoint.
    """
    rules = get_rules()
    # Exclude the 'conditions' callable (not JSON-serialisable)
    serialisable = [
        {
            "id": r["id"],
            "name": r["name"],
            "priority": r["priority"],
            "action": r["action"],
            "explanation_template": r["explanation"],
        }
        for r in rules
    ]
    return jsonify({
        "success": True,
        "count": len(serialisable),
        "rules": serialisable,
    }), 200


@ai_bp.route("/explain/<int:plan_id>", methods=["GET"])
@login_required_api
def explain_plan(plan_id: int):
    """
    Retrieve logged rule explanations for a previously saved plan (scoped to user).
    """
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute("SELECT * FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
    else:
        cursor.execute("SELECT * FROM study_plans WHERE id = ? AND user_id IS NULL", (plan_id,))
    plan = cursor.fetchone()
    if not plan:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Plan with ID {plan_id} was not found."
            }
        }), 404

    cursor.execute(
        """
        SELECT rl.*, s.name AS subject_name
        FROM rule_logs rl
        LEFT JOIN plan_items pi ON pi.plan_id = rl.plan_id
        LEFT JOIN subjects s ON s.id = pi.subject_id
        WHERE rl.plan_id = ?
        ORDER BY rl.id ASC
        """,
        (plan_id,)
    )
    logs = [dict(row) for row in cursor.fetchall()]

    # Deduplicate by rule_log id
    seen = set()
    unique_logs = []
    for log in logs:
        if log["id"] not in seen:
            seen.add(log["id"])
            unique_logs.append(log)

    return jsonify({
        "success": True,
        "plan_id": plan_id,
        "plan_date": dict(plan)["plan_date"],
        "rule_logs": unique_logs,
        "count": len(unique_logs),
    }), 200


@ai_bp.route("/plan/latest", methods=["GET"])
@login_required_api
def get_latest_plan():
    """
    Retrieve the most recently generated study plan with all its items for active user.
    """
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT id FROM study_plans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    else:
        cursor.execute("SELECT id FROM study_plans WHERE user_id IS NULL ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        return jsonify({
            "success": True,
            "message": "No study plans found. Generate a plan first via POST /api/ai/plan.",
            "plan": None
        }), 200

    plan = _fetch_plan_with_items(conn, row["id"], user_id=user_id)
    return jsonify({
        "success": True,
        "plan": plan
    }), 200


@ai_bp.route("/plan/<int:plan_id>", methods=["GET"])
@login_required_api
def get_plan_by_id(plan_id: int):
    """
    Retrieve a specific study plan and its sessions by ID for active user.
    """
    user_id = get_current_user_id()
    conn = get_db_connection()
    plan = _fetch_plan_with_items(conn, plan_id, user_id=user_id)

    if not plan:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Plan with ID {plan_id} was not found."
            }
        }), 404

    return jsonify({
        "success": True,
        "plan": plan
    }), 200


@ai_bp.route("/plan/items/<int:item_id>/complete", methods=["PATCH", "POST"])
@login_required_api
def toggle_item_completion(item_id: int):
    """
    Update completion status of a study session item (0 for pending, 1 for completed).
    Verifies that the plan belongs to the active user.
    """
    user_id = get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute(
            """
            SELECT pi.* FROM plan_items pi
            JOIN study_plans sp ON sp.id = pi.plan_id
            WHERE pi.id = ? AND sp.user_id = ?
            """,
            (item_id, user_id)
        )
    else:
        cursor.execute(
            """
            SELECT pi.* FROM plan_items pi
            JOIN study_plans sp ON sp.id = pi.plan_id
            WHERE pi.id = ? AND sp.user_id IS NULL
            """,
            (item_id,)
        )
    item = cursor.fetchone()
    if not item:
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Study session item with ID {item_id} was not found."
            }
        }), 404

    data = request.get_json(silent=True) or {}
    new_status = 1
    if "is_completed" in data:
        val = data["is_completed"]
        if isinstance(val, bool):
            new_status = 1 if val else 0
        elif isinstance(val, int) and val in (0, 1):
            new_status = val
        else:
            return jsonify({
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "messages": ["'is_completed' must be an integer (0 or 1) or a boolean (true or false)."]
                }
            }), 400

    cursor.execute("UPDATE plan_items SET is_completed = ? WHERE id = ?", (new_status, item_id))
    conn.commit()

    cursor.execute("SELECT * FROM plan_items WHERE id = ?", (item_id,))
    updated_item = dict(cursor.fetchone())

    return jsonify({
        "success": True,
        "message": f"Session item {item_id} marked as {'completed' if new_status == 1 else 'pending'}.",
        "item": updated_item
    }), 200
