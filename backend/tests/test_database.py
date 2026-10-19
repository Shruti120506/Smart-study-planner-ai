"""
Unit tests for SQLite Database initialization, foreign keys, and default records.
"""

import tempfile
from pathlib import Path
import pytest
try:
    from backend.database.db import init_db, get_db_connection, load_sample_subjects
except ImportError:
    from database.db import init_db, get_db_connection, load_sample_subjects


@pytest.fixture
def temp_db():
    """Provides a temporary SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_database_initialization(temp_db):
    """Test that all tables and default preferences are created on init_db."""
    init_db(db_path=temp_db)

    conn = get_db_connection(db_path=temp_db)
    cursor = conn.cursor()

    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cursor.fetchall()}

    expected_tables = {"subjects", "study_preferences", "study_plans", "plan_items", "rule_logs"}
    assert expected_tables.issubset(tables)

    # Verify default study preferences seeded
    cursor.execute("SELECT * FROM study_preferences")
    pref = cursor.fetchone()
    assert pref is not None
    assert pref["daily_available_hours"] == 4.0
    assert pref["fatigue_level"] == "medium"
    assert pref["preferred_time_of_day"] == "morning"
    assert pref["focus_span_minutes"] == 45
    conn.close()


def test_foreign_key_enforcement(temp_db):
    """Test that foreign key constraint prevents orphan plan_items."""
    init_db(db_path=temp_db)
    conn = get_db_connection(db_path=temp_db)
    cursor = conn.cursor()

    # Attempt inserting a plan_item referencing non-existent plan_id and subject_id
    with pytest.raises(Exception):
        cursor.execute(
            """
            INSERT INTO plan_items (plan_id, subject_id, session_title, allocated_minutes)
            VALUES (999, 999, 'Invalid Session', 45)
            """
        )
    conn.close()


def test_load_sample_subjects_deduplication(temp_db):
    """Test that loading sample subjects does not create duplicate entries."""
    init_db(db_path=temp_db)

    # First load
    first_res = load_sample_subjects(db_path=temp_db)
    assert first_res["added_count"] > 0
    assert first_res["skipped_count"] == 0

    # Second load - all should be skipped
    second_res = load_sample_subjects(db_path=temp_db)
    assert second_res["added_count"] == 0
    assert second_res["skipped_count"] == first_res["added_count"]
