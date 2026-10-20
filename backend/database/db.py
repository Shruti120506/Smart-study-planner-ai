"""
Database Management Module for Smart Study Planner AI.
Supports both SQLite (local development and tests) and PostgreSQL (production on Render).
Preserves existing SQLite functionality, local data, queries, and row factory conventions.
"""

import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import current_app, g

# Optional PostgreSQL driver imports
try:
    import pg8000.dbapi as pg8000_dbapi
except ImportError:
    pg8000_dbapi = None

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

# Default database location inside 'instance/' folder at project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "planner.db"
SCHEMA_FILE_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_PG_FILE_PATH = Path(__file__).resolve().parent / "schema_pg.sql"


def is_postgres_url(url: str | None) -> bool:
    """Checks whether a database URL points to a PostgreSQL database."""
    if not url:
        return False
    clean_url = url.strip().lower()
    return clean_url.startswith("postgresql://") or clean_url.startswith("postgres://")


def get_database_url() -> str | None:
    """Retrieves the active DATABASE_URL if configured in environment or app config."""
    db_url = None
    if current_app:
        db_url = current_app.config.get("DATABASE_URL")
    if not db_url:
        db_url = os.environ.get("DATABASE_URL")
    return db_url.strip() if db_url else None


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


def _translate_sql_params_for_postgres(sql: str) -> str:
    """
    Carefully replaces '?' parameter markers with '%s' format specifiers for PostgreSQL,
    ignoring '?' characters that appear inside single-quoted string literals, double-quoted
    identifiers, or line/block comments.
    """
    parts = []
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        # Single-quoted string literal (with '' escape handling)
        if c == "'":
            end = i + 1
            while end < n:
                if sql[end] == "'":
                    if end + 1 < n and sql[end + 1] == "'":
                        end += 2
                    else:
                        end += 1
                        break
                else:
                    end += 1
            parts.append(sql[i:end])
            i = end
        # Double-quoted identifier
        elif c == '"':
            end = i + 1
            while end < n and sql[end] != '"':
                end += 1
            if end < n:
                end += 1
            parts.append(sql[i:end])
            i = end
        # Single-line comment (-- ...)
        elif c == '-' and i + 1 < n and sql[i + 1] == '-':
            end = sql.find('\n', i)
            if end == -1:
                end = n
            parts.append(sql[i:end])
            i = end
        # Parameter marker
        elif c == '?':
            parts.append('%s')
            i += 1
        else:
            parts.append(c)
            i += 1
    return "".join(parts)


class PostgresRow:
    """
    A dict-like and indexable row representation mirroring sqlite3.Row.
    Allows accessing fields by case-insensitive column name or index.
    """
    def __init__(self, description, values):
        self._values = list(values)
        self._col_names = [col[0] for col in description] if description else []
        self._col_map = {name.lower(): idx for idx, name in enumerate(self._col_names)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, str):
            idx = self._col_map.get(key.lower())
            if idx is not None:
                return self._values[idx]
        raise KeyError(f"Column '{key}' not found in row.")

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._col_names)

    def values(self):
        return list(self._values)

    def items(self):
        return list(zip(self._col_names, self._values))

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __repr__(self):
        return f"<PostgresRow {dict(self.items())}>"


class PostgresCursorAdapter:
    """
    Cursor adapter wrapping a DB-API cursor (psycopg2 or pg8000).
    Provides:
    - Automatic translation of '?' to '%s'
    - cursor.lastrowid support for INSERT statements (via RETURNING id)
    - sqlite3.Row-compatible row fetching
    """
    def __init__(self, raw_cursor, is_pg8000=False):
        self._raw_cursor = raw_cursor
        self._is_pg8000 = is_pg8000
        self.lastrowid = None
        self._pending_id_capture = False

    def __getattr__(self, name):
        return getattr(self._raw_cursor, name)

    @property
    def description(self):
        return self._raw_cursor.description

    @property
    def rowcount(self):
        return self._raw_cursor.rowcount

    def execute(self, sql, params=None):
        self.lastrowid = None
        self._pending_id_capture = False
        translated_sql = _translate_sql_params_for_postgres(sql)

        # Check if this is an INSERT statement needing primary key capture for cursor.lastrowid
        stripped = translated_sql.strip()
        is_insert = re.match(r"^INSERT\s+INTO\b", stripped, re.IGNORECASE) is not None
        has_returning = re.search(r"\bRETURNING\b", stripped, re.IGNORECASE) is not None

        if is_insert and not has_returning:
            translated_sql = f"{translated_sql} RETURNING id"
            self._pending_id_capture = True

        if params is not None:
            if isinstance(params, list):
                params = tuple(params)
            self._raw_cursor.execute(translated_sql, params)
        else:
            self._raw_cursor.execute(translated_sql)

        if self._pending_id_capture:
            # Capture generated ID from RETURNING id
            res = self._raw_cursor.fetchone()
            if res:
                self.lastrowid = res[0]
            self._pending_id_capture = False

        return self

    def executemany(self, sql, seq_of_params):
        translated_sql = _translate_sql_params_for_postgres(sql)
        return self._raw_cursor.executemany(translated_sql, seq_of_params)

    def fetchone(self):
        row = self._raw_cursor.fetchone()
        if row is None:
            return None
        return PostgresRow(self._raw_cursor.description, row)

    def fetchall(self):
        rows = self._raw_cursor.fetchall()
        desc = self._raw_cursor.description
        return [PostgresRow(desc, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._raw_cursor.fetchmany(size) if size is not None else self._raw_cursor.fetchmany()
        desc = self._raw_cursor.description
        return [PostgresRow(desc, r) for r in rows]

    def close(self):
        return self._raw_cursor.close()


class PostgresConnectionAdapter:
    """
    Connection adapter wrapping a PostgreSQL connection (psycopg2 or pg8000).
    Provides execute(), cursor(), commit(), rollback(), close() with standard interface.
    """
    def __init__(self, raw_conn, is_pg8000=False):
        self._raw_conn = raw_conn
        self._is_pg8000 = is_pg8000

    def cursor(self):
        raw_cur = self._raw_conn.cursor()
        return PostgresCursorAdapter(raw_cur, is_pg8000=self._is_pg8000)

    def execute(self, sql, params=None):
        """Allows direct execution on connection: conn.execute(...)"""
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    def close(self):
        return self._raw_conn.close()


def connect_postgres(url: str):
    """
    Establishes a connection to PostgreSQL using psycopg2 if available, or pg8000 as fallback.
    Handles Render URL prefix 'postgres://' by standardizing to 'postgresql://'.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    # 1. Try psycopg2 if available
    if psycopg2 is not None:
        try:
            conn = psycopg2.connect(url)
            return PostgresConnectionAdapter(conn, is_pg8000=False)
        except Exception:
            # Fall back to pg8000 if psycopg2 has runtime/DLL issues
            pass

    # 2. Try pg8000
    if pg8000_dbapi is not None:
        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)

        user = parsed.username or "postgres"
        password = parsed.password or ""
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        database = parsed.path.lstrip("/") or "postgres"

        ssl_context = True if query_params.get("sslmode", [""])[0] in ("require", "verify-ca", "verify-full") else None

        conn = pg8000_dbapi.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl_context=ssl_context
        )
        return PostgresConnectionAdapter(conn, is_pg8000=True)

    raise RuntimeError(
        "PostgreSQL connection requested via DATABASE_URL, but neither psycopg2 nor pg8000 is available."
    )


def get_db_connection(db_path=None):
    """
    Opens and returns a database connection.
    - If DATABASE_URL is set and points to Postgres, connects to PostgreSQL.
    - Otherwise (default), connects to SQLite at db_path or instance/planner.db.
    Enables foreign keys and row factory for dict-like row access.
    Within a Flask request context, reuses g.db to avoid duplicate connections.
    """
    db_url = get_database_url()

    # Route 1: PostgreSQL Connection
    if is_postgres_url(db_url):
        if current_app:
            if "db" not in g:
                g.db = connect_postgres(db_url)
            return g.db
        return connect_postgres(db_url)

    # Route 2: SQLite Connection (Default)
    target_path = get_db_path(db_path)

    if current_app:
        if "db" not in g:
            conn = sqlite3.connect(target_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            g.db = conn
        return g.db

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
    from single-tenant to multi-tenant authenticated schema on SQLite.
    Checks table structures and adds or relaxes user_id columns without losing data.
    """
    # Only run SQLite-specific table inspection on SQLite connections
    if not isinstance(conn, sqlite3.Connection):
        return

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
    cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    first_user = cursor.fetchone()
    if first_user and first_user[0] is not None:
        primary_user_id = first_user[0]
        cursor.execute("UPDATE subjects SET user_id = ? WHERE user_id IS NULL", (primary_user_id,))
        cursor.execute("UPDATE study_plans SET user_id = ? WHERE user_id IS NULL", (primary_user_id,))

        cursor.execute("SELECT id FROM study_preferences WHERE user_id = ?", (primary_user_id,))
        user_pref_exists = cursor.fetchone()

        cursor.execute("SELECT * FROM study_preferences WHERE user_id IS NULL ORDER BY id ASC LIMIT 1")
        legacy_pref = cursor.fetchone()

        if legacy_pref:
            if user_pref_exists:
                cursor.execute(
                    """
                    UPDATE study_preferences 
                    SET daily_available_hours = ?, preferred_time_of_day = ?, focus_span_minutes = ?, fatigue_level = ?
                    WHERE user_id = ?
                    """,
                    (legacy_pref["daily_available_hours"], legacy_pref["preferred_time_of_day"], legacy_pref["focus_span_minutes"], legacy_pref["fatigue_level"], primary_user_id)
                )
            else:
                cursor.execute(
                    "UPDATE study_preferences SET user_id = ? WHERE id = ?",
                    (primary_user_id, legacy_pref["id"])
                )

    conn.commit()


def init_db(app=None, db_path=None):
    """
    Initializes database tables using the appropriate schema (schema.sql for SQLite,
    schema_pg.sql for PostgreSQL), executes migrations safely, and seeds default preferences.
    """
    db_url = get_database_url()

    # Route 1: PostgreSQL Initialization
    if is_postgres_url(db_url):
        conn = connect_postgres(db_url)
        try:
            if SCHEMA_PG_FILE_PATH.exists():
                with open(SCHEMA_PG_FILE_PATH, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                # Execute individual DDL statements safely
                statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
                for stmt in statements:
                    conn.execute(stmt)
                conn.commit()

            # Seed global default student preferences (user_id IS NULL) if none exist
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS count FROM study_preferences WHERE user_id IS NULL")
            row = cur.fetchone()
            if row and row["count"] == 0:
                conn.execute(
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
        return

    # Route 2: SQLite Initialization (Default)
    target_path = get_db_path(db_path)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        migrate_db_schema(conn)

        with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        migrate_db_schema(conn)

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

    if not current_app:
        conn.close()

    return {
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added_subjects": added,
        "skipped_subjects": skipped
    }
