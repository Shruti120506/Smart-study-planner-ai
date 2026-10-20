# 🎓 Smart Study Planner AI

> An intelligent, **Rule-Based Artificial Intelligence (Expert System)** web application designed to help college students optimize study schedules, manage academic fatigue, and verify exam goals.

---

## 📌 Project Overview

Unlike generic calendar applications that only store dates, **Smart Study Planner AI** uses a symbolic AI inference engine (Forward Chaining and Backward Chaining) to:
- Automatically calculate personalized daily study schedules based on subject difficulty, urgency, and fatigue.
- Explain every decision in plain English (e.g., *"Why did the AI allocate 2 hours to Math and only 45 mins to English?"*).
- Check whether academic goals (e.g., scoring an 'A' grade or finishing the syllabus) are mathematically feasible before exam day.

---

## 🛠️ Technology Stack

- **Frontend:** HTML5, CSS3 (Modern Responsive UI), JavaScript (Vanilla ES6) *(Phase 5)*
- **Backend:** Python with Flask & Flask-CORS
- **Database:** SQLite with foreign keys and parameterized SQL
- **AI Engine:** Custom Rule-Based Inference Engine in Python (Forward & Backward Chaining) *(Phase 3)*
- **Testing:** pytest automated test suite
- **Version Control:** Git & GitHub

---

## 🚀 Current Milestone: Phase 4 (REST API Integration & Verification Complete)

Phase 4 completes the integration and verification of the full REST API suite connecting the Flask backend, SQLite persistence, and Rule-Based AI Engine (Forward & Backward Chaining). The test suite boasts **101 passing automated tests**.

### 📁 Project Structure

```text
Smart-Study-Planner/
├── backend/
│   ├── __init__.py                 # Backend package identifier
│   ├── app.py                      # Flask server entrypoint, blueprint registration & discovery
│   ├── database/
│   │   ├── __init__.py             # Database exports
│   │   ├── db.py                   # Reusable SQLite connection & helper methods
│   │   └── schema.sql              # Clean SQLite table definitions & foreign keys
│   ├── routes/
│   │   ├── __init__.py             # Routes package exports
│   │   ├── subjects_bp.py          # /api/subjects CRUD & sample seeder
│   │   ├── preferences_bp.py       # /api/preferences endpoints
│   │   ├── ai_bp.py                # /api/ai endpoints (plan, goals, rules, explain, completion)
│   │   └── validators.py           # Input validation for subjects and preferences
│   ├── ai/
│   │   ├── __init__.py             # AI package
│   │   ├── knowledge_base.py       # Explicit IF-THEN rules with explanations
│   │   ├── working_memory.py       # Subject facts, time limits, and state tracking
│   │   ├── forward_chainer.py      # Match-resolve-act forward inference scheduler
│   │   ├── backward_chainer.py     # Goal-driven sub-goal verifier and deficit analyzer
│   │   └── explanation_generator.py # Template-based plain-English explanation renderer
│   └── tests/
│       ├── __init__.py             # Tests package
│       ├── test_health.py          # Health check & root discovery tests
│       ├── test_database.py        # Schema, foreign keys, & deduplication tests
│       ├── test_subjects_crud.py   # Subject CRUD & validation rule tests
│       ├── test_preferences.py     # Study preferences tests
│       ├── test_ai_engine.py       # AI Engine unit tests (forward, backward, explain, competition)
│       └── test_api_integration.py # Phase 4 full REST API integration & verification tests
├── frontend/                       # User interface (coming in Phase 5)
├── instance/                       # SQLite database directory (auto-created, gitignored)
│   └── planner.db                  # Local SQLite database file
├── .gitignore                      # Files ignored by Git (venv, *.db, pycache)
├── requirements.txt                # Python package dependencies
└── README.md                       # Beginner-friendly documentation & testing guide
```

---

## 📋 Comprehensive API Endpoints Table

| Category | Method | Endpoint | Description | Request Body Example | Success Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System** | `GET` | `/` | Root API discovery & phase information | _None_ | `200 OK` |
| **System** | `GET` | `/api/health` | Health & SQLite connectivity check | _None_ | `200 OK` |
| **Subjects** | `GET` | `/api/subjects` | List all enrolled subjects with progress % | _None_ | `200 OK` |
| **Subjects** | `POST` | `/api/subjects` | Create a new subject | `{"name":"Linear Algebra","difficulty_level":"hard","target_grade":"A","exam_date":"2026-11-20","syllabus_units_total":6,"units_completed":1}` | `201 Created` |
| **Subjects** | `GET` | `/api/subjects/<id>` | Retrieve a single subject by ID | _None_ | `200 OK` |
| **Subjects** | `PUT` | `/api/subjects/<id>` | Update an existing subject | `{"units_completed":3}` | `200 OK` |
| **Subjects** | `DELETE`| `/api/subjects/<id>` | Delete an academic subject | _None_ | `200 OK` |
| **Subjects** | `POST` | `/api/subjects/sample` | Seed 5 college subjects with dynamic exam dates | _None_ | `200 OK` |
| **Preferences**| `GET`| `/api/preferences` | Retrieve current student preferences | _None_ | `200 OK` |
| **Preferences**| `PUT`/`POST`| `/api/preferences` | Update study hours, fatigue, focus span | `{"daily_available_hours":4.5,"fatigue_level":"medium","preferred_time_of_day":"morning","focus_span_minutes":45}` | `200 OK` |
| **AI Planner** | `POST` | `/api/ai/plan` | Generate today's schedule via Forward Chaining | `{"save": true}` | `200 OK` |
| **AI Planner** | `GET` | `/api/ai/plan/latest` | Retrieve the latest active plan & session items | _None_ | `200 OK` |
| **AI Planner** | `GET` | `/api/ai/plan/<plan_id>` | Retrieve a historical plan by ID | _None_ | `200 OK` |
| **AI Planner** | `PATCH`/`POST`| `/api/ai/plan/items/<item_id>/complete` | Toggle session item completion (1=done, 0=pending) | `{"is_completed": 1}` or `{"is_completed": false}` | `200 OK` |
| **AI Goals** | `POST` | `/api/ai/goals` | Analyze exam goal feasibility via Backward Chaining | Optional: `{"subject_id": 1}` or `{}` for all | `200 OK` |
| **AI Rules** | `GET` | `/api/ai/rules` | List all IF-THEN rules in Knowledge Base | _None_ | `200 OK` |
| **AI Explain** | `GET` | `/api/ai/explain/<plan_id>` | Retrieve fired rule audit logs for viva defense | _None_ | `200 OK` |

---

## 💻 Setup & Testing Instructions for Windows (PowerShell)

### Step 1: Open PowerShell and Activate Virtual Environment
## 🚀 Current Milestone: Phase 5 (Interactive Student Dashboard UI Complete)

Phase 5 delivers a complete, responsive frontend dashboard designed with clean student-first UI aesthetics. It directly interfaces with the Flask REST APIs and custom AI Engine without any external build step or complex node tooling. The automated test suite boasts **103 passing tests**.

### 📁 Project Structure

```text
Smart-Study-Planner/
├── backend/
│   ├── __init__.py                 # Backend package identifier
│   ├── app.py                      # Flask server, static asset serving & API discovery
│   ├── database/
│   │   ├── __init__.py             # Database exports
│   │   ├── db.py                   # Reusable SQLite connection & helper methods
│   │   └── schema.sql              # Clean SQLite table definitions & foreign keys
│   ├── routes/
│   │   ├── __init__.py             # Routes package exports
│   │   ├── subjects_bp.py          # /api/subjects CRUD & sample seeder
│   │   ├── preferences_bp.py       # /api/preferences endpoints
│   │   ├── ai_bp.py                # /api/ai endpoints (plan, goals, rules, explain, completion)
│   │   └── validators.py           # Input validation for subjects and preferences
│   ├── ai/
│   │   ├── __init__.py             # AI package
│   │   ├── knowledge_base.py       # Explicit IF-THEN rules with explanations
│   │   ├── working_memory.py       # Subject facts, time limits, and state tracking
│   │   ├── forward_chainer.py      # Match-resolve-act forward inference scheduler
│   │   ├── backward_chainer.py     # Goal-driven sub-goal verifier and deficit analyzer
│   │   └── explanation_generator.py # Template-based plain-English explanation renderer
│   └── tests/
│       ├── __init__.py             # Tests package
│       ├── test_health.py          # Health check & root discovery tests
│       ├── test_database.py        # Schema, foreign keys, & deduplication tests
│       ├── test_subjects_crud.py   # Subject CRUD & validation rule tests
│       ├── test_preferences.py     # Study preferences tests
│       ├── test_ai_engine.py       # AI Engine unit tests (forward, backward, explain, competition)
│       └── test_api_integration.py # Full REST API integration & frontend serving tests
├── frontend/                       # User interface
│   ├── index.html                  # Responsive Student Dashboard layout
│   ├── style.css                   # Modern CSS styling with design system variables
│   └── app.js                      # Async Fetch API interactions & state management
├── instance/                       # SQLite database directory (auto-created, gitignored)
│   └── planner.db                  # Local SQLite database file
├── .gitignore                      # Files ignored by Git (venv, *.db, pycache)
├── requirements.txt                # Python package dependencies
└── README.md                       # Documentation & setup guide
```

---

## 💻 Setup & Running the Application on Windows (PowerShell)

### Step 1: Open PowerShell and Activate Virtual Environment
```powershell
cd C:\Users\Admin\Desktop\Smart-Study-Planner
.\.venv\Scripts\Activate.ps1
```

### Step 2: Run the Full Automated Test Suite (103 Passing Tests)
Execute either `unittest` or `pytest`:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```
*(All 103 tests pass across database initialization, subjects CRUD, preferences, AI engine forward/backward chaining, and frontend integration).*

### Step 3: Start the Flask Backend Server
```powershell
python backend\app.py
```
The server will start at:
- **Interactive Student Dashboard:** `http://127.0.0.1:5000/dashboard` (or open `http://127.0.0.1:5000` directly in your browser)
- **API Base:** `http://127.0.0.1:5000/api`

---

## 🎨 Dashboard Features (Phase 5)

1. **Dashboard Overview & Metrics**: Real-time summary cards displaying enrolled course count, daily study budget, sessions scheduled today, and completion percentage.
2. **1-Click Sample Course Seeder**: Instantly populates standard college courses with dynamic upcoming exam dates.
3. **Subject Management (CRUD)**: Create, edit, and delete subjects with target grades, difficulty weights, and syllabus unit tracking.
4. **Study Preferences & Fatigue Configuration**: Easily set daily study hours (0.5h–16h), focus spans (15m–120m), and fatigue levels (`low`, `medium`, `high`).
5. **AI Schedule Generation**: One-click Forward Chaining AI scheduler creates today's timetable with recommended time slots and cognitive break allocations.
6. **Task Completion Checkboxes**: Check off study sessions dynamically, with updates persisting to the database and recalculating progress bars.
7. **Exam Goal Feasibility Analyzer**: Real-time Backward Chaining verifies whether your target grades and syllabus units are achievable before exam dates.
8. **Explainable AI Viva Inspector**: View firing rule IDs, matched conditions, and natural-language explanations for viva voce defense.

---

## 🗺️ Next Roadmap Phases

- **Phase 6:** End-to-End Edge Cases & Stress Testing
- **Phase 7:** College Presentation & Viva Voce Defense Preparation
