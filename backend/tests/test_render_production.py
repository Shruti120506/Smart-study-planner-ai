"""
Unit and integration tests for Render production readiness, PostgreSQL adapter,
and configuration security guardrails.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from backend.app import create_app
from backend.database.db import (
    _translate_sql_params_for_postgres,
    PostgresRow,
    PostgresCursorAdapter,
    PostgresConnectionAdapter,
    is_postgres_url,
    SCHEMA_PG_FILE_PATH,
    init_db,
    get_db_connection,
)


class PostgresAdapterAndSecurityTestCase(unittest.TestCase):
    """Verifies database adapter behaviors, SQL parameter translation, row access, and production config."""

    def test_postgres_url_detection(self):
        """Verify PostgreSQL connection URL detection logic."""
        self.assertTrue(is_postgres_url("postgresql://user:pass@localhost:5432/db"))
        self.assertTrue(is_postgres_url("postgres://user:pass@render.com/db"))
        self.assertFalse(is_postgres_url(None))
        self.assertFalse(is_postgres_url(""))
        self.assertFalse(is_postgres_url("sqlite:///instance/planner.db"))

    def test_translate_sql_params_for_postgres(self):
        """Verify SQL parameter marker substitution (? -> %s) ignores string literals and comments."""
        # Case 1: Simple parameters
        sql1 = "SELECT * FROM subjects WHERE id = ? AND user_id = ?"
        self.assertEqual(
            _translate_sql_params_for_postgres(sql1),
            "SELECT * FROM subjects WHERE id = %s AND user_id = %s"
        )

        # Case 2: Question mark inside single quotes should NOT be replaced
        sql2 = "SELECT 'Is this a question?' AS q, id FROM subjects WHERE id = ? AND name = 'What?'"
        self.assertEqual(
            _translate_sql_params_for_postgres(sql2),
            "SELECT 'Is this a question?' AS q, id FROM subjects WHERE id = %s AND name = 'What?'"
        )

        # Case 3: Question mark with escaped quotes inside literals
        sql3 = "SELECT 'It''s a ? mark' AS val FROM users WHERE email = ?"
        self.assertEqual(
            _translate_sql_params_for_postgres(sql3),
            "SELECT 'It''s a ? mark' AS val FROM users WHERE email = %s"
        )

        # Case 4: Question mark inside double-quoted identifiers or SQL comments
        sql4 = "-- Does this comment have a ? mark\nSELECT * FROM t WHERE a = ?"
        self.assertEqual(
            _translate_sql_params_for_postgres(sql4),
            "-- Does this comment have a ? mark\nSELECT * FROM t WHERE a = %s"
        )

    def test_postgres_row_dict_and_index_access(self):
        """Verify PostgresRow behaves like sqlite3.Row for dict-like and index-based access."""
        description = [
            ("id", 23, None, None, None, None, None),
            ("name", 1043, None, None, None, None, None),
            ("DAILY_AVAILABLE_HOURS", 701, None, None, None, None, None),
        ]
        values = (42, "Computer Science", 5.5)
        row = PostgresRow(description, values)

        # Index access
        self.assertEqual(row[0], 42)
        self.assertEqual(row[1], "Computer Science")
        self.assertEqual(row[2], 5.5)

        # Case-insensitive name access
        self.assertEqual(row["id"], 42)
        self.assertEqual(row["name"], "Computer Science")
        self.assertEqual(row["daily_available_hours"], 5.5)
        self.assertEqual(row["DAILY_AVAILABLE_HOURS"], 5.5)

        # Keys, values, items, get
        self.assertEqual(row.keys(), ["id", "name", "DAILY_AVAILABLE_HOURS"])
        self.assertEqual(row.values(), [42, "Computer Science", 5.5])
        self.assertEqual(row.get("name"), "Computer Science")
        self.assertEqual(row.get("non_existent", "default_val"), "default_val")

        with self.assertRaises(KeyError):
            _ = row["unknown_column"]

    def test_postgres_cursor_adapter_lastrowid_capture(self):
        """Verify PostgresCursorAdapter automatically appends RETURNING id on INSERT and captures lastrowid."""
        mock_raw_cursor = MagicMock()
        mock_raw_cursor.description = [("id", 23)]
        mock_raw_cursor.fetchone.return_value = (999,)

        adapter = PostgresCursorAdapter(mock_raw_cursor)
        adapter.execute("INSERT INTO subjects (user_id, name) VALUES (?, ?)", (1, "Math"))

        # Verify SQL was translated with RETURNING id and %s
        called_sql, called_params = mock_raw_cursor.execute.call_args[0]
        self.assertIn("RETURNING id", called_sql)
        self.assertIn("%s", called_sql)
        self.assertEqual(called_params, (1, "Math"))
        self.assertEqual(adapter.lastrowid, 999)

    def test_postgres_cursor_adapter_non_insert_statements(self):
        """Verify non-INSERT statements (SELECT, UPDATE, DELETE) do not have RETURNING id appended."""
        mock_raw_cursor = MagicMock()
        mock_raw_cursor.description = [("id", 23), ("name", 1043)]
        mock_raw_cursor.fetchall.return_value = [(1, "Chemistry")]

        adapter = PostgresCursorAdapter(mock_raw_cursor)
        adapter.execute("SELECT * FROM subjects WHERE id = ?", (1,))

        called_sql = mock_raw_cursor.execute.call_args[0][0]
        self.assertNotIn("RETURNING id", called_sql)
        self.assertIn("WHERE id = %s", called_sql)
        self.assertIsNone(adapter.lastrowid)

        rows = adapter.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Chemistry")

    def test_postgres_connection_adapter_transaction_methods(self):
        """Verify PostgresConnectionAdapter forwards commit, rollback, and close to the raw connection."""
        mock_raw_conn = MagicMock()
        conn_adapter = PostgresConnectionAdapter(mock_raw_conn)

        conn_adapter.commit()
        mock_raw_conn.commit.assert_called_once()

        conn_adapter.rollback()
        mock_raw_conn.rollback.assert_called_once()

        conn_adapter.close()
        mock_raw_conn.close.assert_called_once()

    def test_postgres_schema_pg_syntax_and_structure(self):
        """Verify that backend/database/schema_pg.sql exists, is readable, and contains all required tables."""
        self.assertTrue(SCHEMA_PG_FILE_PATH.exists(), "schema_pg.sql must exist")
        with open(SCHEMA_PG_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        expected_tables = ["users", "subjects", "study_preferences", "study_plans", "plan_items", "rule_logs"]
        for tbl in expected_tables:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {tbl}", content)

        # Confirm PostgreSQL-specific SERIAL PRIMARY KEY is used instead of AUTOINCREMENT
        self.assertIn("SERIAL PRIMARY KEY", content)
        self.assertNotIn("AUTOINCREMENT", content)
        self.assertNotIn("COLLATE NOCASE", content)

    def test_production_missing_secret_key_fails(self):
        """Verify that create_app raises RuntimeError when FLASK_ENV=production but SECRET_KEY is missing/default."""
        orig_env = os.environ.get("FLASK_ENV")
        orig_render = os.environ.get("RENDER")
        orig_key = os.environ.get("SECRET_KEY")

        try:
            os.environ["FLASK_ENV"] = "production"
            if "RENDER" in os.environ:
                del os.environ["RENDER"]

            # Scenario 1: Empty / missing SECRET_KEY
            if "SECRET_KEY" in os.environ:
                del os.environ["SECRET_KEY"]

            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("CRITICAL PRODUCTION SECURITY ERROR", str(ctx.exception))

            # Scenario 2: Using the old hardcoded default secret key
            os.environ["SECRET_KEY"] = "smart-study-planner-secret-key-production-ready-2026"
            with self.assertRaises(RuntimeError) as ctx2:
                create_app()
            self.assertIn("CRITICAL PRODUCTION SECURITY ERROR", str(ctx2.exception))

            # Scenario 3: Secret key too short (< 32 chars)
            os.environ["SECRET_KEY"] = "short-key-12345"
            with self.assertRaises(RuntimeError) as ctx3:
                create_app()
            self.assertIn("CRITICAL PRODUCTION SECURITY ERROR", str(ctx3.exception))
        finally:
            if orig_env is not None:
                os.environ["FLASK_ENV"] = orig_env
            else:
                os.environ.pop("FLASK_ENV", None)

            if orig_render is not None:
                os.environ["RENDER"] = orig_render
            else:
                os.environ.pop("RENDER", None)

            if orig_key is not None:
                os.environ["SECRET_KEY"] = orig_key
            else:
                os.environ.pop("SECRET_KEY", None)

    def test_production_secure_cookie_and_proxyfix(self):
        """Verify that with valid production settings, HTTPS secure cookies and ProxyFix are applied."""
        orig_env = os.environ.get("FLASK_ENV")
        orig_key = os.environ.get("SECRET_KEY")

        try:
            os.environ["FLASK_ENV"] = "production"
            os.environ["SECRET_KEY"] = "super-secret-random-key-with-more-than-32-characters"

            app = create_app()
            self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
            self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
            self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
            # Verify ProxyFix is in the wsgi middleware stack
            self.assertEqual(app.wsgi_app.__class__.__name__, "ProxyFix")
        finally:
            if orig_env is not None:
                os.environ["FLASK_ENV"] = orig_env
            else:
                os.environ.pop("FLASK_ENV", None)

            if orig_key is not None:
                os.environ["SECRET_KEY"] = orig_key
            else:
                os.environ.pop("SECRET_KEY", None)

    def test_local_development_default_database(self):
        """Confirm that in default local development mode, SQLite is selected without error."""
        app = create_app()
        self.assertFalse(app.config["SESSION_COOKIE_SECURE"])
        self.assertIn("planner.db", app.config["DATABASE"])


if __name__ == "__main__":
    unittest.main()
