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

- **Frontend:** HTML5, CSS3 (Modern Responsive UI), JavaScript (Vanilla ES6)
- **Backend:** Python with Flask & Flask-CORS
- **Database:** SQLite (Lightweight, serverless)
- **AI Engine:** Custom Rule-Based Inference Engine in Python (Forward & Backward Chaining)
- **Version Control:** Git & GitHub

---

## 🚀 Current Milestone: Phase 1 (Foundation Setup)

Phase 1 establishes the core backend environment and a health-check endpoint.

### 📁 Project Structure

```text
Smart-Study-Planner/
├── backend/
│   └── app.py              # Flask server entrypoint & API endpoints
├── frontend/               # User interface (coming in later phases)
├── .gitignore              # Files ignored by Git (venv, *.db, pycache)
├── requirements.txt        # Python package dependencies
└── README.md               # Project documentation & instructions
```

---

## 💻 Setup Instructions for Windows (PowerShell)

Follow these exact steps to run the application on Windows:

### Step 1: Open PowerShell in the Project Directory
Make sure your terminal is opened in `Smart-Study-Planner`:
```powershell
cd C:\Users\Admin\Desktop\Smart-Study-Planner
```

### Step 2: Create a Virtual Environment
A virtual environment keeps the project libraries isolated from your global Python installation:
```powershell
python -m venv venv
```

### Step 3: Activate the Virtual Environment
Activate the environment in your PowerShell window:
```powershell
.\venv\Scripts\Activate.ps1
```
> **Note:** If Windows blocks script execution with an error like `cannot be loaded because running scripts is disabled`, run this one-time command in PowerShell and try activating again:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\venv\Scripts\Activate.ps1
> ```
*(You will see `(venv)` appear at the start of your terminal line when active).*

### Step 4: Install Dependencies
Install Flask and testing tools:
```powershell
pip install -r requirements.txt
```

### Step 5: Start the Flask Backend Server
```powershell
python backend\app.py
```
You will see output indicating that the Flask server is running at:
`http://127.0.0.1:5000`

---

## 🧪 Testing the Health-Check Endpoint

While the server is running, open your web browser or open a **new PowerShell window** and test the endpoints:

### In a Web Browser:
- Visit: [http://127.0.0.1:5000/](http://127.0.0.1:5000/) — Home welcome route
- Visit: [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health) — Health check endpoint

### In PowerShell:
```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

**Expected JSON Response:**
```json
{
  "service": "Smart Study Planner AI Backend",
  "status": "healthy",
  "timestamp": "2026-10-19T...",
  "uptime_status": "ok"
}
```

---

## 🗺️ Next Roadmap Phases

- **Phase 2:** SQLite Database Setup (`schema.sql` and `db.py`)
- **Phase 3:** Custom Rule-Based AI Engine (Working Memory, Rules, Forward & Backward Chaining)
- **Phase 4:** REST API Routes (Subjects, Daily Preferences, Schedule Generation)
- **Phase 5:** Interactive Student Dashboard UI
- **Phase 6:** Automated Unit Tests & Error Handling
- **Phase 7:** Cloud Deployment & College Presentation / Viva Prep
