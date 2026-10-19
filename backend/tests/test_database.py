"""
Unit tests for SQLite Database initialization, foreign keys, and default records using unittest.TestCase
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(TESTS_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.database.db import init_db, get_db_connection, load_sample_subjects
except ImportError:
    from database.db import init_db, get_db_connection, load_sample_subjects


class DatabaseInitializationTestCase(unittest.TestCase):
    """Tests SQLite database tables, constraints, and seeding."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        init_db(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_database_initialization(self):
        """Verify that all core tables and default preferences are created."""
        conn = get_db_connection(db_path=self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        expected = {"subjects", "study_preferences", "study_plans", "plan_items", "rule_logs"}
        self.assertTrue(expected.issubset(tables))

    def test_default_preferences_seeded(self):
        """Verify that default preferences row is inserted upon initialization."""
        conn = get_db_connection(db_path=self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM study_preferences")
        pref = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(pref)
        self.assertEqual(pref["daily_available_hours"], 4.0)
        self.assertEqual(pref["fatigue_level"], "medium")
        self.assertEqual(pref["preferred_time_of_day"], "morning")
        self.assertEqual(pref["focus_span_minutes"], 45)

    def test_foreign_key_enforcement(self):
        """Verify that foreign keys prevent orphan plan_items."""
        conn = get_db_connection(db_path=self.db_path)
        cursor = conn.cursor()
        with self.assertRaises(Exception):
            cursor.execute(
                """
                INSERT INTO plan_items (plan_id, subject_id, session_title, allocated_minutes)
                VALUES (999, 999, 'Invalid Session', 45)
                """
            )
        conn.close()

    def test_load_sample_subjects_deduplication(self):
        """Verify sample subjects load without creating duplicates."""
        first_load = load_sample_subjects(db_path=self.db_path)
        self.assertGreater(first_load["added_count"], 0)
        self.assertEqual(first_load["skipped_count"], 0)

        second_load = load_sample_subjects(db_path=self.db_path)
        self.assertEqual(second_load["added_count"], 0)
        self.assertEqual(second_load["skipped_count"], first_load["added_count"])


if __name__ == "__main__":
    unittest.main()
