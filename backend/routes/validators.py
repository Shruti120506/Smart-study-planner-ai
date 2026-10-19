"""
Input Validation Module for Smart Study Planner AI
Validates subject parameters, study preferences, and dates with clear error messages.
"""

from datetime import datetime


def validate_subject_payload(data, is_update=False, existing_subject=None):
    """
    Validates subject data for creation or update.
    Returns: (is_valid: bool, errors: list[str], cleaned_data: dict)
    """
    errors = []
    cleaned = {}

    if not isinstance(data, dict):
        return False, ["Request body must be a valid JSON object."], {}

    # 1. Validate Name
    if not is_update or "name" in data:
        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("Subject name is required and cannot be empty.")
        elif len(name.strip()) > 100:
            errors.append("Subject name cannot exceed 100 characters.")
        else:
            cleaned["name"] = name.strip()

    # 2. Validate Difficulty Level
    if not is_update or "difficulty_level" in data:
        difficulty = data.get("difficulty_level", "medium")
        if not isinstance(difficulty, str) or difficulty.lower() not in ["easy", "medium", "hard"]:
            errors.append("Difficulty level must be one of: 'easy', 'medium', 'hard'.")
        else:
            cleaned["difficulty_level"] = difficulty.lower()

    # 3. Validate Target Grade
    if not is_update or "target_grade" in data:
        target_grade = data.get("target_grade", "A")
        if not isinstance(target_grade, str) or not target_grade.strip():
            errors.append("Target grade must be a non-empty string.")
        elif len(target_grade.strip()) > 10:
            errors.append("Target grade cannot exceed 10 characters.")
        else:
            cleaned["target_grade"] = target_grade.strip().upper()

    # 4. Validate Exam Date
    if not is_update or "exam_date" in data:
        exam_date = data.get("exam_date")
        if exam_date:
            if not isinstance(exam_date, str):
                errors.append("Exam date must be a string formatted as YYYY-MM-DD.")
            else:
                try:
                    parsed_date = datetime.strptime(exam_date.strip(), "%Y-%m-%d").date()
                    today = datetime.now().date()
                    if parsed_date < today:
                        errors.append(f"Exam date ({exam_date}) cannot be in the past.")
                    else:
                        cleaned["exam_date"] = parsed_date.isoformat()
                except ValueError:
                    errors.append("Exam date must be a valid calendar date in YYYY-MM-DD format.")
        else:
            cleaned["exam_date"] = None

    # 5. Validate Syllabus Units
    total_units = None
    completed_units = None

    if not is_update or "syllabus_units_total" in data:
        total_val = data.get("syllabus_units_total", 5 if not is_update else None)
        try:
            total_units = int(total_val)
            if total_units <= 0:
                errors.append("Total syllabus units must be greater than 0.")
            elif total_units > 100:
                errors.append("Total syllabus units cannot exceed 100.")
            else:
                cleaned["syllabus_units_total"] = total_units
        except (ValueError, TypeError):
            errors.append("Total syllabus units must be an integer.")
    elif existing_subject:
        total_units = existing_subject["syllabus_units_total"]

    if not is_update or "units_completed" in data:
        completed_val = data.get("units_completed", 0 if not is_update else None)
        try:
            completed_units = int(completed_val)
            if completed_units < 0:
                errors.append("Completed syllabus units cannot be negative.")
            else:
                cleaned["units_completed"] = completed_units
        except (ValueError, TypeError):
            errors.append("Completed syllabus units must be an integer.")
    elif existing_subject:
        completed_units = existing_subject["units_completed"]

    # Comparative check: completed cannot exceed total
    final_total = total_units if total_units is not None else (existing_subject["syllabus_units_total"] if existing_subject else 5)
    final_completed = completed_units if completed_units is not None else (existing_subject["units_completed"] if existing_subject else 0)

    if final_total is not None and final_completed is not None:
        if final_completed > final_total:
            errors.append(
                f"Units completed ({final_completed}) cannot exceed total units ({final_total})."
            )

    return (len(errors) == 0, errors, cleaned)


def validate_preferences_payload(data):
    """
    Validates study preferences payload.
    Returns: (is_valid: bool, errors: list[str], cleaned_data: dict)
    """
    errors = []
    cleaned = {}

    if not isinstance(data, dict):
        return False, ["Preferences payload must be a JSON object."], {}

    if "daily_available_hours" in data:
        try:
            hours = float(data["daily_available_hours"])
            if hours < 0.5 or hours > 16.0:
                errors.append("Daily available study hours must be between 0.5 and 16.0 hours.")
            else:
                cleaned["daily_available_hours"] = round(hours, 2)
        except (ValueError, TypeError):
            errors.append("Daily available study hours must be a number.")

    if "preferred_time_of_day" in data:
        pref_time = data["preferred_time_of_day"]
        if not isinstance(pref_time, str) or pref_time.lower() not in ["morning", "afternoon", "night"]:
            errors.append("Preferred time of day must be 'morning', 'afternoon', or 'night'.")
        else:
            cleaned["preferred_time_of_day"] = pref_time.lower()

    if "focus_span_minutes" in data:
        try:
            span = int(data["focus_span_minutes"])
            if span < 15 or span > 120:
                errors.append("Focus span must be between 15 and 120 minutes.")
            else:
                cleaned["focus_span_minutes"] = span
        except (ValueError, TypeError):
            errors.append("Focus span must be an integer (minutes).")

    if "fatigue_level" in data:
        fatigue = data["fatigue_level"]
        if not isinstance(fatigue, str) or fatigue.lower() not in ["low", "medium", "high"]:
            errors.append("Fatigue level must be 'low', 'medium', or 'high'.")
        else:
            cleaned["fatigue_level"] = fatigue.lower()

    return (len(errors) == 0, errors, cleaned)
