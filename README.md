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

## 🚀 Current Milestone: Phase 2 (SQLite Database & Persistence Complete)

Phase 2 introduces automated database management, schema constraints, student preferences, and full REST CRUD endpoints for academic subjects.

### 📁 Project Structure

```text
Smart-Study-Planner/
├── backend/
│   ├── __init__.py                 # Backend package identifier
│   ├── app.py                      # Flask server entrypoint & blueprint registration
│   ├── database/
│   │   ├── __init__.py             # Database exports
│   │   ├── db.py                   # Reusable SQLite connection & helper methods
│   │   └── schema.sql              # Clean SQLite table definitions & foreign keys
│   ├── routes/
│   │   ├── __init__.py             # Routes package exports
│   │   ├── subjects_bp.py          # /api/subjects CRUD & sample seeder
│   │   ├── preferences_bp.py       # /api/preferences endpoints
│   │   └── validators.py           # Input validation for subjects and preferences
│   └── tests/
│       ├── __init__.py             # Tests package
│       ├── test_health.py          # Health check endpoint tests
│       ├── test_database.py        # Schema, foreign keys, & deduplication tests
│       ├── test_subjects_crud.py   # Subject CRUD & validation rule tests
│       └── test_preferences.py     # Study preferences tests
├── frontend/                       # User interface (coming in Phase 5)
├── instance/                       # SQLite database directory (auto-created, gitignored)
│   └── planner.db                  # Local SQLite database file
├── .gitignore                      # Files ignored by Git (venv, *.db, pycache)
├── requirements.txt                # Python package dependencies
└── README.md                       # Beginner-friendly documentation & testing guide
```

---

## 💻 Setup Instructions for Windows (PowerShell)

Follow these exact steps to run the application on Windows:

### Step 1: Open PowerShell in the Project Directory
```powershell
cd C:\Users\Admin\Desktop\Smart-Study-Planner
```

### Step 2: Activate the Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```
*(If you see an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and then run the activate command again).*

### Step 3: Install Dependencies (if not already installed)
```powershell
pip install -r requirements.txt
```

### Step 4: Run the Automated Pytest Suite
Run the 18 automated unit and integration tests to verify database initialization, validation, and API routes:
```powershell
python -m pytest -v
```
*(All 18 tests will pass with green checkmarks).*

### Step 5: Start the Flask Backend Server
```powershell
python backend\app.py
```
The server will automatically initialize `instance/planner.db` and listen at:
`http://127.0.0.1:5000`

---

## 🧪 Testing the API Endpoints via PowerShell

With the server running in your first PowerShell window, open a **second PowerShell window** and test the endpoints:

### 1. Health & Database Connectivity Check
```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```
**Response:**
```json
{
  "database": "connected",
  "service": "Smart Study Planner AI Backend",
  "status": "healthy",
  "uptime_status": "ok"
}
```

### 2. Load Sample College Subjects (1-Click Seed)
```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:5000/api/subjects/sample
```
Populates 5 standard college courses (*Data Structures, DBMS, OS, Networks, Web Dev*) with dynamic upcoming exam dates without creating duplicates.

### 3. List All Enrolled Subjects (Enriched with Progress & Exam Countdown)
```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/subjects
```

### 4. Create a New Subject (with Validation)
```powershell
$newSubject = @{
    name = "Artificial Intelligence"
    difficulty_level = "hard"
    target_grade = "A"
    exam_date = "2026-11-15"
    syllabus_units_total = 5
    units_completed = 1
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/subjects -ContentType "application/json" -Body $newSubject
```

### 5. Update an Existing Subject Progress
```powershell
$updatePayload = @{ units_completed = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:5000/api/subjects/1 -ContentType "application/json" -Body $updatePayload
```

### 6. Delete a Subject
```powershell
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:5000/api/subjects/5
```

### 7. View & Update Study Preferences (Hours & Fatigue)
**View Preferences:**
```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/preferences
```
**Update Preferences:**
```powershell
$prefs = @{
    daily_available_hours = 5.0
    fatigue_level = "high"
    preferred_time_of_day = "morning"
    focus_span_minutes = 30
} | ConvertTo-Json

Invoke-RestMethod -Method Put -Uri http://127.0.0.1:5000/api/preferences -ContentType "application/json" -Body $prefs
```

---

## 🗺️ Next Roadmap Phases

- **Phase 3:** Custom Rule-Based AI Engine (Working Memory, Fact Base, Forward & Backward Chaining Inference)
- **Phase 4:** REST API Routes for AI Reasoning (`/api/ai/generate-plan` & `/api/ai/check-goal`)
- **Phase 5:** Interactive Student Dashboard UI (HTML, CSS, JavaScript)
- **Phase 6:** End-to-End Testing & Boundary Conditions
- **Phase 7:** Cloud Deployment & College Presentation / Viva Defense Preparation
