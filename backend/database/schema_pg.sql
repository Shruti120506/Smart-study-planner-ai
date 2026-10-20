-- Smart Study Planner AI Database Schema (PostgreSQL)
-- User Authentication and Multi-Tenant Isolation for Production on Render

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

-- 2. Subjects Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    name VARCHAR(255) NOT NULL,
    difficulty_level VARCHAR(32) NOT NULL DEFAULT 'medium' CHECK(difficulty_level IN ('easy', 'medium', 'hard')),
    target_grade VARCHAR(10) NOT NULL DEFAULT 'A',
    exam_date VARCHAR(32), -- Stored as ISO format YYYY-MM-DD
    syllabus_units_total INTEGER NOT NULL DEFAULT 5 CHECK(syllabus_units_total > 0),
    units_completed INTEGER NOT NULL DEFAULT 0 CHECK(units_completed >= 0 AND units_completed <= syllabus_units_total),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_user_name ON subjects (user_id, LOWER(name));
CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects (user_id);

-- 3. Student Preferences Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS study_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    daily_available_hours DOUBLE PRECISION NOT NULL DEFAULT 4.0 CHECK(daily_available_hours >= 0.5 AND daily_available_hours <= 16.0),
    preferred_time_of_day VARCHAR(32) NOT NULL DEFAULT 'morning' CHECK(preferred_time_of_day IN ('morning', 'afternoon', 'night')),
    focus_span_minutes INTEGER NOT NULL DEFAULT 45 CHECK(focus_span_minutes >= 15 AND focus_span_minutes <= 120),
    fatigue_level VARCHAR(32) NOT NULL DEFAULT 'medium' CHECK(fatigue_level IN ('low', 'medium', 'high')),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_preferences_user ON study_preferences (user_id);

-- 4. Study Plans Table (Scoped by user_id)
CREATE TABLE IF NOT EXISTS study_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    plan_date VARCHAR(32) NOT NULL, -- Format: YYYY-MM-DD
    total_hours_allocated DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK(total_hours_allocated >= 0.0),
    strategy_used VARCHAR(64) DEFAULT 'standard',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_study_plans_user ON study_plans (user_id);

-- 5. Plan Items Table (Individual Study Sessions in a Plan)
CREATE TABLE IF NOT EXISTS plan_items (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    session_title VARCHAR(255) NOT NULL,
    allocated_minutes INTEGER NOT NULL CHECK(allocated_minutes > 0),
    break_minutes INTEGER NOT NULL DEFAULT 10 CHECK(break_minutes >= 0),
    priority VARCHAR(32) NOT NULL DEFAULT 'MEDIUM' CHECK(priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    session_type VARCHAR(64) NOT NULL DEFAULT 'new_concept' CHECK(session_type IN ('new_concept', 'revision', 'practice_problems', 'emergency_cram')),
    recommended_time_slot VARCHAR(64),
    fired_rule_id VARCHAR(64),
    is_completed SMALLINT NOT NULL DEFAULT 0 CHECK(is_completed IN (0, 1)),
    FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON plan_items (plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_items_subject ON plan_items (subject_id);

-- 6. AI Rule Execution Logs (Transparency and Explainability for Viva)
CREATE TABLE IF NOT EXISTS rule_logs (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER,
    rule_id VARCHAR(64) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    condition_matched TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    logged_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_rule_logs_plan ON rule_logs (plan_id);
