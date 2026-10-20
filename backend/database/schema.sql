-- Smart Study Planner AI Database Schema (SQLite)
-- User Authentication and Multi-Tenant Isolation

PRAGMA foreign_keys = ON;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Subjects Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT NOT NULL COLLATE NOCASE,
    difficulty_level TEXT CHECK(difficulty_level IN ('easy', 'medium', 'hard')) NOT NULL DEFAULT 'medium',
    target_grade TEXT NOT NULL DEFAULT 'A',
    exam_date TEXT, -- Stored as ISO format YYYY-MM-DD
    syllabus_units_total INTEGER NOT NULL DEFAULT 5 CHECK(syllabus_units_total > 0),
    units_completed INTEGER NOT NULL DEFAULT 0 CHECK(units_completed >= 0 AND units_completed <= syllabus_units_total),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_user_name ON subjects (user_id, LOWER(name));

-- 3. Student Preferences Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS study_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    daily_available_hours REAL NOT NULL DEFAULT 4.0 CHECK(daily_available_hours >= 0.5 AND daily_available_hours <= 16.0),
    preferred_time_of_day TEXT CHECK(preferred_time_of_day IN ('morning', 'afternoon', 'night')) NOT NULL DEFAULT 'morning',
    focus_span_minutes INTEGER NOT NULL DEFAULT 45 CHECK(focus_span_minutes >= 15 AND focus_span_minutes <= 120),
    fatigue_level TEXT CHECK(fatigue_level IN ('low', 'medium', 'high')) NOT NULL DEFAULT 'medium',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_preferences_user ON study_preferences (user_id);

-- 4. Study Plans Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS study_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan_date TEXT NOT NULL, -- Format: YYYY-MM-DD
    total_hours_allocated REAL NOT NULL DEFAULT 0.0 CHECK(total_hours_allocated >= 0.0),
    strategy_used TEXT DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 5. Plan Items Table (Individual Study Sessions in a Plan)
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    session_title TEXT NOT NULL,
    allocated_minutes INTEGER NOT NULL CHECK(allocated_minutes > 0),
    break_minutes INTEGER NOT NULL DEFAULT 10 CHECK(break_minutes >= 0),
    priority TEXT CHECK(priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')) NOT NULL DEFAULT 'MEDIUM',
    session_type TEXT CHECK(session_type IN ('new_concept', 'revision', 'practice_problems', 'emergency_cram')) NOT NULL DEFAULT 'new_concept',
    recommended_time_slot TEXT,
    fired_rule_id TEXT,
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK(is_completed IN (0, 1)),
    FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

-- 6. AI Rule Execution Logs (Transparency and Explainability for Viva)
CREATE TABLE IF NOT EXISTS rule_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    condition_matched TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE SET NULL
);
