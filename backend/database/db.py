"""
Database Management Module for Smart Study Planner AI
Handles SQLite connections, schema initialization, sample data, and query helpers.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import current_app, g

# Default database location inside 'instance/' folder at project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "planner.db"
SCHEMA_FILE_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db_path(custom_path=None):
    """
    Resolves the SQLite database path.
    Prioritizes:
    1. Explicit custom_path argument
    2. Flask current_app.config['DATABASE'] if within application context
    3. DEFAULT_DB_PATH (instance/planner.db)
    """
    if custom_path:
        db_path = Path(custom_path)
    elif current_app and current_app.config.get("DATABASE"):
        db_path = Path(current_app.config["DATABASE"])
    else:
        db_path = DEFAULT_DB_PATH

    # Ensure parent directory exists (e.g. instance/)
    os.makedirs(db_path.parent, exist_ok=True)
    return db_path


def get_db_connection(db_path=None):
    """
    Opens and returns a SQLite database connection.
    Enables foreign keys and row factory for dict-like row access.
    Within a Flask request context, reuses g.db to avoid duplicate connections.
    """
    target_path = get_db_path(db_path)

    # If within Flask request context, cache in `g`
    if current_app:
        if "db" not in g:
            conn = sqlite3.connect(target_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            g.db = conn
        return g.db

    # Standalone connection (outside Flask request context, e.g. tests/scripts)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def close_db_connection(e=None):
    """Closes the current database connection stored in Flask g context."""
    db = g.pop("db", None) if current_app else None
    if db is not None:
        db.close()


def init_db(app=None, db_path=None):
    """
    Initializes SQLite tables using schema.sql and seeds default preferences if missing.
    Can be called directly or with a Flask app instance.
    """
    target_path = get_db_path(db_path)

    # Use a direct connection to ensure schema execution
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # Seed default student preferences if none exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM study_preferences")
        row = cursor.fetchone()
        if row and row["count"] == 0:
            cursor.execute(
                """
                INSERT INTO study_preferences 
                (daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level)
                VALUES (?, ?, ?, ?)
                """,
                (4.0, "morning", 45, "medium")
            )
        conn.commit()
    finally:
        conn.close()


def load_sample_subjects(db_path=None):
    """
    Populates sample academic subjects for realistic demonstration.
    Checks by name before inserting to prevent duplicates.
    Returns a dictionary summarizing items added and skipped.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    today = datetime.now().date()

    # Pre-defined realistic college subjects with dynamically calculated upcoming exam dates
    sample_data = [
        {
            "name": "Data Structures & Algorithms",
            "difficulty_level": "hard",
            "target_grade": "A",
            "exam_date": (today + timedelta(days=3)).isoformat(),
            "syllabus_units_total": 6,
            "units_completed": 2
        },
        {
            "name": "Database Management Systems",
            "difficulty_level": "medium",
            "target_grade": "A",
            "exam_date": (today + timedelta(days=7)).isoformat(),
            "syllabus_units_total": 5,
            "units_completed": 3
        },
        {
            "name": "Operating Systems",
            "difficulty_level": "hard",
            "target_grade": "A",
            "exam_date": (today + timedelta(days=5)).isoformat(),
            "syllabus_units_total": 5,
            "units_completed": 1
        },
        {
            "name": "Computer Networks",
            "difficulty_level": "medium",
            "target_grade": "B",
            "exam_date": (today + timedelta(days=12)).isoformat(),
            "syllabus_units_total": 5,
            "units_completed": 4
        },
        {
            "name": "Web Development",
            "difficulty_level": "easy",
            "target_grade": "A",
            "exam_date": (today + timedelta(days=16)).isoformat(),
            "syllabus_units_total": 4,
            "units_completed": 3
        }
    ]

    added = []
    skipped = []

    for item in sample_data:
        cursor.execute("SELECT id FROM subjects WHERE LOWER(name) = LOWER(?)", (item["name"],))
        existing = cursor.fetchone()
        if existing:
            skipped.append(item["name"])
        else:
            cursor.execute(
                """
                INSERT INTO subjects (name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["name"],
                    item["difficulty_level"],
                    item["target_grade"],
                    item["exam_date"],
                    item["syllabus_units_total"],
                    item["units_completed"]
                )
            )
            added.append(item["name"])

    conn.commit()

    # Close if outside request context
    if not current_app:
        conn.close()

    return {
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added_subjects": added,
        "skipped_subjects": skipped
    }
