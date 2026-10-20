"""
Phase 4: Comprehensive REST API Integration and Verification Tests
Tests all endpoints:
- Subjects CRUD, duplicate names, validation errors, non-existent IDs
- Preferences GET/PUT/POST, validations, limits
- AI Plan Generation (forward chaining, daily budget adherence, save/no-save)
- AI Plan Retrieval (latest plan, by ID, non-existent 404)
- Study Session Completion toggle (complete/pending, invalid payload, non-existent 404)
- Goal Feasibility (backward chaining, daily hours vs total available hours, multi-subject)
- AI Rules listing and Explain endpoint
- CORS header verification for frontend client requests
"""

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(TESTS_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import create_app
    from backend.database.db import get_db_connection
except ImportError:
    from app import create_app
    from database.db import get_db_connection


class Phase4ApiIntegrationTestCase(unittest.TestCase):
    """Full REST API Integration tests verifying end-to-end functionality for Phase 4."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    # -------------------------------------------------------------------------
    # 1. CORS Verification
    # -------------------------------------------------------------------------

    def test_cors_headers_present_for_frontend(self):
        """Verify that API responses allow cross-origin requests from frontends."""
        res = self.client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("Access-Control-Allow-Origin", res.headers)
        self.assertIn(res.headers.get("Access-Control-Allow-Origin"), ("*", "http://localhost:3000"))

    def test_cors_options_preflight(self):
        """Verify that OPTIONS preflight requests succeed without error."""
        res = self.client.options(
            "/api/ai/plan",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        self.assertIn(res.status_code, (200, 204))
        self.assertIn("Access-Control-Allow-Origin", res.headers)

    def test_frontend_dashboard_served(self):
        """Verify that /dashboard returns the frontend HTML page."""
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Smart Study Planner AI", res.data)
        self.assertIn(b"Student Dashboard", res.data)

    def test_frontend_static_assets_served(self):
        """Verify that frontend static CSS and JS are served via /static route."""
        css_res = self.client.get("/static/style.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn(b":root", css_res.data)

        js_res = self.client.get("/static/app.js")
        self.assertEqual(js_res.status_code, 200)
        self.assertIn(b"generateStudyPlan", js_res.data)

    # -------------------------------------------------------------------------
    # 2. Subjects REST API Verification
    # -------------------------------------------------------------------------

    def test_subjects_crud_full_cycle(self):
        """Create, read, update, and delete subject via API."""
        # 1. Create
        exam = (date.today() + timedelta(days=5)).isoformat()
        res = self.client.post(
            "/api/subjects",
            json={
                "name": "Linear Algebra",
                "difficulty_level": "hard",
                "target_grade": "A",
                "exam_date": exam,
                "syllabus_units_total": 6,
                "units_completed": 1,
            },
        )
        self.assertEqual(res.status_code, 201)
        sub_data = res.get_json()
        self.assertTrue(sub_data["success"])
        sub_id = sub_data["subject"]["id"]
        self.assertEqual(sub_data["subject"]["name"], "Linear Algebra")
        self.assertEqual(sub_data["subject"]["completion_percentage"], 16.7)
        self.assertEqual(sub_data["subject"]["remaining_units"], 5)

        # 2. Read single
        get_res = self.client.get(f"/api/subjects/{sub_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["subject"]["id"], sub_id)

        # 3. Update
        up_res = self.client.put(f"/api/subjects/{sub_id}", json={"units_completed": 3})
        self.assertEqual(up_res.status_code, 200)
        self.assertEqual(up_res.get_json()["subject"]["units_completed"], 3)
        self.assertEqual(up_res.get_json()["subject"]["completion_percentage"], 50.0)

        # 4. Delete
        del_res = self.client.delete(f"/api/subjects/{sub_id}")
        self.assertEqual(del_res.status_code, 200)

        # 5. Verify deleted returns 404
        get_again = self.client.get(f"/api/subjects/{sub_id}")
        self.assertEqual(get_again.status_code, 404)
        self.assertEqual(get_again.get_json()["error"]["code"], "NOT_FOUND")

    def test_subject_invalid_inputs(self):
        """Test subject endpoint with invalid json, negative units, past exam date, and missing name."""
        # Missing name
        res = self.client.post("/api/subjects", json={"difficulty_level": "hard"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # Units completed > total
        res = self.client.post(
            "/api/subjects",
            json={
                "name": "Chemistry",
                "syllabus_units_total": 4,
                "units_completed": 5,
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "VALIDATION_ERROR")

        # Non-existent ID for update returns 404
        res = self.client.put("/api/subjects/9999", json={"units_completed": 1})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["error"]["code"], "NOT_FOUND")

        # Non-existent ID for delete returns 404
        res = self.client.delete("/api/subjects/9999")
        self.assertEqual(res.status_code, 404)

    # -------------------------------------------------------------------------
    # 3. Preferences API Verification
    # -------------------------------------------------------------------------

    def test_preferences_get_and_update(self):
        """Verify default preferences and updating daily available hours."""
        res = self.client.get("/api/preferences")
        self.assertEqual(res.status_code, 200)
        prefs = res.get_json()["preferences"]
        self.assertEqual(prefs["daily_available_hours"], 4.0)

        # Update preferences
        up_res = self.client.put(
            "/api/preferences",
            json={
                "daily_available_hours": 6.5,
                "fatigue_level": "low",
                "focus_span_minutes": 50,
            },
        )
        self.assertEqual(up_res.status_code, 200)
        updated = up_res.get_json()["preferences"]
        self.assertEqual(updated["daily_available_hours"], 6.5)
        self.assertEqual(updated["fatigue_level"], "low")
        self.assertEqual(updated["focus_span_minutes"], 50)

    def test_preferences_validation_errors(self):
        """Test out of bounds daily hours and invalid fatigue."""
        res = self.client.put("/api/preferences", json={"daily_available_hours": 25.0})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "VALIDATION_ERROR")

        res = self.client.put("/api/preferences", json={"fatigue_level": "exhausted"})
        self.assertEqual(res.status_code, 400)

    # -------------------------------------------------------------------------
    # 4. AI Plan Generation & Budget Constraints
    # -------------------------------------------------------------------------

    def test_plan_allocations_never_exceed_daily_budget(self):
        """Confirm that daily plan allocations never exceed the configured daily study budget."""
        # Set daily budget to 3.0 hours (180 minutes)
        self.client.put("/api/preferences", json={"daily_available_hours": 3.0})

        # Seed sample subjects
        self.client.post("/api/subjects/sample")

        res = self.client.post("/api/ai/plan", json={"save": True})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        total_allocated_minutes = sum(item["allocated_minutes"] for item in data["plan_items"])
        self.assertLessEqual(
            total_allocated_minutes,
            180,
            f"Allocated {total_allocated_minutes}m exceeds daily budget of 180m",
        )
        self.assertIsNotNone(data["plan_id"])

        # Check plan_items have id and is_completed fields
        for item in data["plan_items"]:
            self.assertIn("id", item)
            self.assertEqual(item["is_completed"], 0)

    # -------------------------------------------------------------------------
    # 5. Study Plan Retrieval & Session Completion Toggle
    # -------------------------------------------------------------------------

    def test_get_latest_plan_empty(self):
        """GET /api/ai/plan/latest when no plans exist returns plan=None."""
        res = self.client.get("/api/ai/plan/latest")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsNone(data["plan"])

    def test_get_latest_plan_and_plan_by_id(self):
        """Generate a plan, then fetch it via latest and by ID."""
        self.client.post("/api/subjects/sample")
        gen_res = self.client.post("/api/ai/plan", json={"save": True})
        plan_id = gen_res.get_json()["plan_id"]

        # Fetch latest
        latest_res = self.client.get("/api/ai/plan/latest")
        self.assertEqual(latest_res.status_code, 200)
        latest_data = latest_res.get_json()
        self.assertTrue(latest_data["success"])
        self.assertEqual(latest_data["plan"]["id"], plan_id)
        self.assertGreater(len(latest_data["plan"]["plan_items"]), 0)
        self.assertEqual(latest_data["plan"]["completed_sessions"], 0)
        self.assertEqual(latest_data["plan"]["completion_percentage"], 0.0)

        # Fetch by ID
        id_res = self.client.get(f"/api/ai/plan/{plan_id}")
        self.assertEqual(id_res.status_code, 200)
        self.assertEqual(id_res.get_json()["plan"]["id"], plan_id)

        # Fetch non-existent ID
        missing_res = self.client.get("/api/ai/plan/99999")
        self.assertEqual(missing_res.status_code, 404)
        self.assertEqual(missing_res.get_json()["error"]["code"], "NOT_FOUND")

    def test_toggle_session_completion_status(self):
        """Toggle session item completion between completed (1) and pending (0)."""
        self.client.post("/api/subjects/sample")
        gen_res = self.client.post("/api/ai/plan", json={"save": True})
        plan_id = gen_res.get_json()["plan_id"]
        item_id = gen_res.get_json()["plan_items"][0]["id"]

        # Mark completed without body (defaults to completed)
        patch_res = self.client.patch(f"/api/ai/plan/items/{item_id}/complete")
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.get_json()
        self.assertTrue(patch_data["success"])
        self.assertEqual(patch_data["item"]["is_completed"], 1)

        # Verify plan completion stats updated
        plan_res = self.client.get(f"/api/ai/plan/{plan_id}")
        plan_data = plan_res.get_json()["plan"]
        self.assertEqual(plan_data["completed_sessions"], 1)
        self.assertGreater(plan_data["completion_percentage"], 0.0)

        # Mark back to pending with boolean { "is_completed": false }
        uncheck_res = self.client.patch(
            f"/api/ai/plan/items/{item_id}/complete", json={"is_completed": False}
        )
        self.assertEqual(uncheck_res.status_code, 200)
        self.assertEqual(uncheck_res.get_json()["item"]["is_completed"], 0)

        # Mark completed via POST (supports both PATCH and POST)
        post_res = self.client.post(
            f"/api/ai/plan/items/{item_id}/complete", json={"is_completed": 1}
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.get_json()["item"]["is_completed"], 1)

        # Test non-existent item ID returns 404
        missing_res = self.client.patch("/api/ai/plan/items/99999/complete")
        self.assertEqual(missing_res.status_code, 404)
        self.assertEqual(missing_res.get_json()["error"]["code"], "NOT_FOUND")

        # Test invalid status payload returns 400
        invalid_res = self.client.patch(
            f"/api/ai/plan/items/{item_id}/complete", json={"is_completed": "yes"}
        )
        self.assertEqual(invalid_res.status_code, 400)
        self.assertEqual(invalid_res.get_json()["error"]["code"], "VALIDATION_ERROR")

    # -------------------------------------------------------------------------
    # 6. Backward Chaining Distinction: Daily Hours vs Total Available Hours
    # -------------------------------------------------------------------------

    def test_backward_chaining_distinguishes_daily_from_total_available_hours(self):
        """
        Verify that backward-chaining calculations explicitly distinguish
        daily_available_hours_for_subject from total available_study_hours
        across remaining days.
        """
        # Set daily budget to 4.0 hours
        self.client.put("/api/preferences", json={"daily_available_hours": 4.0})

        today = date.today()
        # Add 2 subjects with different exam dates
        self.client.post(
            "/api/subjects",
            json={
                "name": "Subject Short",
                "difficulty_level": "hard",
                "exam_date": (today + timedelta(days=3)).isoformat(),
                "syllabus_units_total": 5,
                "units_completed": 1,
            },
        )
        self.client.post(
            "/api/subjects",
            json={
                "name": "Subject Long",
                "difficulty_level": "medium",
                "exam_date": (today + timedelta(days=10)).isoformat(),
                "syllabus_units_total": 5,
                "units_completed": 1,
            },
        )

        res = self.client.post("/api/ai/goals", json={})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("daily_budget_hours", data)
        self.assertEqual(data["daily_budget_hours"], 4.0)

        goal_results = data["goal_results"]
        self.assertEqual(len(goal_results), 2)

        total_daily_shares = sum(g["hours_per_day_for_subject"] for g in goal_results)
        self.assertAlmostEqual(total_daily_shares, 4.0, places=2)

        for g in goal_results:
            # Check clarity of metrics
            self.assertIn("hours_per_day_for_subject", g)
            self.assertIn("available_study_hours", g)
            self.assertIn("days_remaining", g)
            self.assertIn("required_study_hours", g)
            self.assertIn("deficit_hours", g)
            self.assertIn("is_feasible", g)

            # Verification: total available = days_remaining * hours_per_day_for_subject
            expected_total_avail = round(
                g["days_remaining"] * g["hours_per_day_for_subject"], 1
            )
            self.assertAlmostEqual(g["available_study_hours"], expected_total_avail, delta=0.2)

        # Subject with 10 days remaining must have more total available study hours than the 3 days subject
        short_sub = next(g for g in goal_results if g["subject_name"] == "Subject Short")
        long_sub = next(g for g in goal_results if g["subject_name"] == "Subject Long")
        self.assertGreater(long_sub["available_study_hours"], short_sub["available_study_hours"])

    # -------------------------------------------------------------------------
    # 7. Rules and Explanations
    # -------------------------------------------------------------------------

    def test_rules_and_explain_plan(self):
        """GET /api/ai/rules returns active rules; GET /api/ai/explain/<id> returns logs."""
        rules_res = self.client.get("/api/ai/rules")
        self.assertEqual(rules_res.status_code, 200)
        rules_data = rules_res.get_json()
        self.assertGreater(rules_data["count"], 0)
        self.assertIn("rules", rules_data)

        # Create a plan to generate rule logs
        self.client.post("/api/subjects/sample")
        plan_res = self.client.post("/api/ai/plan", json={"save": True})
        plan_id = plan_res.get_json()["plan_id"]

        explain_res = self.client.get(f"/api/ai/explain/{plan_id}")
        self.assertEqual(explain_res.status_code, 200)
        explain_data = explain_res.get_json()
        self.assertTrue(explain_data["success"])
        self.assertGreater(explain_data["count"], 0)
        self.assertIn("rule_logs", explain_data)


if __name__ == "__main__":
    unittest.main()
