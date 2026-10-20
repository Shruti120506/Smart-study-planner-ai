"""
Database Management Module for Smart Study Planner AI
Handles SQLite connections, schema initialization, safe migrations, sample data, and query helpers.
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


def migrate_db_schema(conn):
    """
    Safe, idempotent schema migration to preserve existing user data when upgrading
    from single-tenant to multi-tenant authenticated schema.
    Checks table structures and adds or relaxes user_id columns without losing data.
    """
    cursor = conn.cursor()

    # 1. Ensure users table exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Helper function to get detailed column info for a table: {col_name: {'notnull': bool, 'type': str}}
    def get_column_details(table_name):
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1]: {"notnull": bool(row[3]), "type": row[2]} for row in cursor.fetchall()}

    # 2. Check subjects table for user_id and multi-tenant unique constraint
    subject_details = get_column_details("subjects")
    if subject_details:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='subjects'")
        subjects_sql_row = cursor.fetchone()
        subjects_sql = subjects_sql_row[0] if subjects_sql_row else ""
        has_global_name_unique = "name TEXT NOT NULL UNIQUE" in subjects_sql or "name TEXT UNIQUE" in subjects_sql
        user_id_not_null = subject_details.get("user_id", {}).get("notnull", False)

        if "user_id" not in subject_details:
            cursor.execute("ALTER TABLE subjects ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects (user_id)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_user_name ON subjects (user_id, LOWER(name))")
        elif has_global_name_unique or user_id_not_null:
            # Upgrade single-tenant table definition to multi-tenant scoped unique (user_id, LOWER(name))
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute(
                """
                CREATE TABLE subjects_migration_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL COLLATE NOCASE,
                    difficulty_level TEXT CHECK(difficulty_level IN ('easy', 'medium', 'hard')) NOT NULL DEFAULT 'medium',
                    target_grade TEXT NOT NULL DEFAULT 'A',
                    exam_date TEXT,
                    syllabus_units_total INTEGER NOT NULL DEFAULT 5 CHECK(syllabus_units_total > 0),
                    units_completed INTEGER NOT NULL DEFAULT 0 CHECK(units_completed >= 0 AND units_completed <= syllabus_units_total),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO subjects_migration_temp (id, user_id, name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed, created_at, updated_at)
                SELECT id, user_id, name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed, created_at, updated_at FROM subjects
                """
            )
            cursor.execute("DROP TABLE subjects")
            cursor.execute("ALTER TABLE subjects_migration_temp RENAME TO subjects")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects (user_id)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_user_name ON subjects (user_id, LOWER(name))")
            cursor.execute("PRAGMA foreign_keys = ON;")

    # 3. Check study_preferences table for user_id
    pref_details = get_column_details("study_preferences")
    if pref_details:
        if "user_id" not in pref_details:
            cursor.execute("ALTER TABLE study_preferences ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        elif pref_details["user_id"]["notnull"]:
            # Relax NOT NULL on study_preferences.user_id to allow unassigned legacy and default preferences
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute(
                """
                CREATE TABLE study_preferences_migration_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    daily_available_hours REAL NOT NULL DEFAULT 4.0 CHECK(daily_available_hours >= 0.5 AND daily_available_hours <= 16.0),
                    preferred_time_of_day TEXT CHECK(preferred_time_of_day IN ('morning', 'afternoon', 'night')) NOT NULL DEFAULT 'morning',
                    focus_span_minutes INTEGER NOT NULL DEFAULT 45 CHECK(focus_span_minutes >= 15 AND focus_span_minutes <= 120),
                    fatigue_level TEXT CHECK(fatigue_level IN ('low', 'medium', 'high')) NOT NULL DEFAULT 'medium',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO study_preferences_migration_temp (id, user_id, daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level, updated_at)
                SELECT id, user_id, daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level, updated_at FROM study_preferences
                """
            )
            cursor.execute("DROP TABLE study_preferences")
            cursor.execute("ALTER TABLE study_preferences_migration_temp RENAME TO study_preferences")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_study_preferences_user ON study_preferences (user_id)")
            cursor.execute("PRAGMA foreign_keys = ON;")

    # 4. Check study_plans table for user_id
    plan_details = get_column_details("study_plans")
    if plan_details:
        if "user_id" not in plan_details:
            cursor.execute("ALTER TABLE study_plans ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_plans_user ON study_plans (user_id)")
        elif plan_details["user_id"]["notnull"]:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute(
                """
                CREATE TABLE study_plans_migration_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_date TEXT NOT NULL,
                    total_hours_allocated REAL NOT NULL DEFAULT 0.0 CHECK(total_hours_allocated >= 0.0),
                    strategy_used TEXT DEFAULT 'standard',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO study_plans_migration_temp (id, user_id, plan_date, total_hours_allocated, strategy_used, created_at)
                SELECT id, user_id, plan_date, total_hours_allocated, strategy_used, created_at FROM study_plans
                """
            )
            cursor.execute("DROP TABLE study_plans")
            cursor.execute("ALTER TABLE study_plans_migration_temp RENAME TO study_plans")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_plans_user ON study_plans (user_id)")
            cursor.execute("PRAGMA foreign_keys = ON;")

    # 5. Check if there are legacy records and a primary registered user exists
    # Migrate legacy local data to the primary registered student to preserve their historical data
    cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    first_user = cursor.fetchone()
    if first_user and first_user[0] is not None:
        primary_user_id = first_user[0]
        cursor.execute("UPDATE subjects SET user_id = ? WHERE user_id IS NULL", (primary_user_id,))
        cursor.execute("UPDATE study_plans SET user_id = ? WHERE user_id IS NULL", (primary_user_id,))

        # Inspect if primary user already has an active study_preferences row
        cursor.execute("SELECT id FROM study_preferences WHERE user_id = ?", (primary_user_id,))
        user_pref_exists = cursor.fetchone()

        # Find any unassigned legacy preferences row
        cursor.execute("SELECT * FROM study_preferences WHERE user_id IS NULL ORDER BY id ASC LIMIT 1")
        legacy_pref = cursor.fetchone()

        if legacy_pref:
            if user_pref_exists:
                # Primary user already has a row; sync custom values from legacy row without violating uniqueness
                cursor.execute(
                    """
                    UPDATE study_preferences 
                    SET daily_available_hours = ?, preferred_time_of_day = ?, focus_span_minutes = ?, fatigue_level = ?
                    WHERE user_id = ?
                    """,
                    (legacy_pref["daily_available_hours"], legacy_pref["preferred_time_of_day"], legacy_pref["focus_span_minutes"], legacy_pref["fatigue_level"], primary_user_id)
                )
            else:
                # Primary user does not have a preferences row yet; assign ownership of the legacy row
                cursor.execute(
                    "UPDATE study_preferences SET user_id = ? WHERE id = ?",
                    (primary_user_id, legacy_pref["id"])
                )

    conn.commit()


def init_db(app=None, db_path=None):
    """
    Initializes SQLite tables using schema.sql, migrates existing tables safely,
    and seeds default preferences if missing.
    Can be called directly or with a Flask app instance.
    """
    target_path = get_db_path(db_path)

    # Use a direct connection to ensure schema execution
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # First apply safe migration if tables already exist
        migrate_db_schema(conn)

        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # Re-run migration check to ensure all columns exist
        migrate_db_schema(conn)

        # Seed global default student preferences (user_id IS NULL) if none exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM study_preferences WHERE user_id IS NULL")
        row = cursor.fetchone()
        if row and row["count"] == 0:
            cursor.execute(
                """
                INSERT INTO study_preferences 
                (user_id, daily_available_hours, preferred_time_of_day, focus_span_minutes, fatigue_level)
                VALUES (NULL, ?, ?, ?, ?)
                """,
                (4.0, "morning", 45, "medium")
            )
        conn.commit()
    finally:
        conn.close()


def load_sample_subjects(db_path=None, user_id=None):
    """
    Populates sample academic subjects for realistic demonstration.
    Checks by name and user_id before inserting to prevent duplicates.
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
        if user_id is not None:
            cursor.execute(
                "SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND user_id = ?",
                (item["name"], user_id)
            )
        else:
            cursor.execute(
                "SELECT id FROM subjects WHERE LOWER(name) = LOWER(?) AND user_id IS NULL",
                (item["name"],)
            )
        existing = cursor.fetchone()
        if existing:
            skipped.append(item["name"])
        else:
            cursor.execute(
                """
                INSERT INTO subjects (user_id, name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
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
