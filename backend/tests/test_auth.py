"""
Comprehensive test suite for Authentication, Authorization, Session Management,
and Multi-Tenant Data Isolation in Smart Study Planner AI.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
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


class AuthAndDataIsolationTestCase(unittest.TestCase):
    """Test suite verifying Auth, Sessions, Protection, and Multi-Tenant Isolation."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        # Explicitly disable LEGACY_TEST_MODE so login_required_api enforces 401 when unauthenticated
        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.db_path,
            "SECRET_KEY": "test-secret-key-123",
            "LEGACY_TEST_MODE": False
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _register_user(self, name, email, password):
        return self.client.post("/api/auth/register", json={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password
        })

    def _login_user(self, email, password, remember_me=False):
        return self.client.post("/api/auth/login", json={
            "email": email,
            "password": password,
            "remember_me": remember_me
        })

    def test_successful_registration_and_login(self):
        """Test registering a new account and then logging in."""
        res_reg = self._register_user("Alice Johnson", "alice@example.com", "Password123!")
        self.assertEqual(res_reg.status_code, 201)
        data_reg = res_reg.get_json()
        self.assertTrue(data_reg["success"])
        self.assertEqual(data_reg["user"]["email"], "alice@example.com")
        self.assertEqual(data_reg["user"]["name"], "Alice Johnson")
        self.assertNotIn("password_hash", data_reg["user"])

        # Check /api/auth/me returns the active session
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)
        self.assertTrue(res_me.get_json()["authenticated"])

        # Log out
        res_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_logout.status_code, 200)
        self.assertTrue(res_logout.get_json()["success"])

        # Verify no longer authenticated
        res_me_after = self.client.get("/api/auth/me")
        self.assertFalse(res_me_after.get_json()["authenticated"])

        # Log back in
        res_login = self._login_user("alice@example.com", "Password123!")
        self.assertEqual(res_login.status_code, 200)
        self.assertTrue(res_login.get_json()["success"])

    def test_duplicate_registration_rejected(self):
        """Test that duplicate email registration returns 409 Conflict."""
        res1 = self._register_user("Bob User", "bob@example.com", "Password123!")
        self.assertEqual(res1.status_code, 201)

        # Attempt duplicate registration with case variation
        res2 = self._register_user("Bob User 2", "BOB@example.com", "DifferentPassword123!")
        self.assertEqual(res2.status_code, 409)
        data2 = res2.get_json()
        self.assertFalse(data2["success"])
        self.assertEqual(data2["error"]["code"], "DUPLICATE_EMAIL")

    def test_registration_validation_errors(self):
        """Test registration inputs validation: invalid email, short password, mismatched confirmation."""
        # Invalid email
        res1 = self.client.post("/api/auth/register", json={
            "name": "Invalid Email",
            "email": "not-an-email",
            "password": "Password123!",
            "confirm_password": "Password123!"
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn("valid email", res1.get_json()["error"]["messages"][0])

        # Short password
        res2 = self.client.post("/api/auth/register", json={
            "name": "Short Pass",
            "email": "valid@email.com",
            "password": "123",
            "confirm_password": "123"
        })
        self.assertEqual(res2.status_code, 400)

        # Mismatched confirmation
        res3 = self.client.post("/api/auth/register", json={
            "name": "Mismatch",
            "email": "mismatch@email.com",
            "password": "Password123!",
            "confirm_password": "WrongPassword!"
        })
        self.assertEqual(res3.status_code, 400)

    def test_incorrect_password_rejected(self):
        """Test login with wrong password or nonexistent user."""
        self._register_user("Charlie Brown", "charlie@example.com", "CorrectPassword123!")
        self.client.post("/api/auth/logout")

        # Wrong password
        res_wrong = self._login_user("charlie@example.com", "WrongPassword!")
        self.assertEqual(res_wrong.status_code, 401)
        self.assertFalse(res_wrong.get_json()["success"])

        # Nonexistent email
        res_no_user = self._login_user("ghost@example.com", "AnyPassword!")
        self.assertEqual(res_no_user.status_code, 401)

    def test_accessing_protected_pages_without_login(self):
        """Test accessing /dashboard without session redirects to /login."""
        # Unauthenticated request for HTML
        response = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_accessing_protected_apis_without_login(self):
        """Test that private API endpoints return 401 Unauthorized when unauthenticated."""
        endpoints = [
            ("GET", "/api/subjects"),
            ("POST", "/api/subjects"),
            ("GET", "/api/preferences"),
            ("POST", "/api/ai/plan"),
            ("GET", "/api/ai/plan/latest")
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                res = self.client.get(endpoint)
            else:
                res = self.client.post(endpoint, json={})
            self.assertEqual(
                res.status_code, 401,
                f"Endpoint {method} {endpoint} did not return 401 for unauthenticated request."
            )
            self.assertEqual(res.get_json()["error"]["code"], "UNAUTHORIZED")

    def test_user_a_cannot_access_or_modify_user_b_data(self):
        """Strict Multi-Tenant Isolation Test: User A and User B cannot see or modify each other's data."""
        client_a = self.app.test_client()
        client_b = self.app.test_client()

        # Register User A
        res_a = client_a.post("/api/auth/register", json={
            "name": "User Alpha",
            "email": "alpha@example.com",
            "password": "PasswordAlpha123!",
            "confirm_password": "PasswordAlpha123!"
        })
        self.assertEqual(res_a.status_code, 201)

        # Register User B
        res_b = client_b.post("/api/auth/register", json={
            "name": "User Beta",
            "email": "beta@example.com",
            "password": "PasswordBeta123!",
            "confirm_password": "PasswordBeta123!"
        })
        self.assertEqual(res_b.status_code, 201)

        # User A creates a subject
        future_date = (datetime.now().date() + timedelta(days=5)).isoformat()
        res_sub_a = client_a.post("/api/subjects", json={
            "name": "Alpha Deep Learning",
            "difficulty_level": "hard",
            "target_grade": "A",
            "exam_date": future_date,
            "syllabus_units_total": 5,
            "units_completed": 1
        })
        self.assertEqual(res_sub_a.status_code, 201)
        subject_a_id = res_sub_a.get_json()["subject"]["id"]

        # User B lists subjects: User A's subject should NOT be visible
        res_sub_b_list = client_b.get("/api/subjects")
        self.assertEqual(res_sub_b_list.status_code, 200)
        subjects_b = res_sub_b_list.get_json()["subjects"]
        self.assertEqual(len(subjects_b), 0)

        # User B attempts to GET User A's subject by ID: must return 404
        res_get_a_by_b = client_b.get(f"/api/subjects/{subject_a_id}")
        self.assertEqual(res_get_a_by_b.status_code, 404)

        # User B attempts to UPDATE User A's subject: must return 404
        res_update_a_by_b = client_b.put(f"/api/subjects/{subject_a_id}", json={
            "name": "Hacked Subject"
        })
        self.assertEqual(res_update_a_by_b.status_code, 404)

        # User B attempts to DELETE User A's subject: must return 404
        res_delete_a_by_b = client_b.delete(f"/api/subjects/{subject_a_id}")
        self.assertEqual(res_delete_a_by_b.status_code, 404)

        # User A updates preferences
        client_a.put("/api/preferences", json={
            "daily_available_hours": 7.5,
            "fatigue_level": "high"
        })

        # User B preferences should remain separate (default values)
        res_pref_b = client_b.get("/api/preferences")
        self.assertEqual(res_pref_b.status_code, 200)
        pref_b = res_pref_b.get_json()["preferences"]
        self.assertEqual(pref_b["daily_available_hours"], 4.0)
        self.assertEqual(pref_b["fatigue_level"], "medium")

        # User A generates a study plan
        res_plan_a = client_a.post("/api/ai/plan", json={"save": True})
        self.assertEqual(res_plan_a.status_code, 200)
        plan_a_id = res_plan_a.get_json()["plan_id"]
        self.assertIsNotNone(plan_a_id)

        # User B attempts to access User A's plan by ID: must return 404
        res_plan_b_access = client_b.get(f"/api/ai/plan/{plan_a_id}")
        self.assertEqual(res_plan_b_access.status_code, 404)

        # User B's latest plan is empty
        res_plan_b_latest = client_b.get("/api/ai/plan/latest")
        self.assertEqual(res_plan_b_latest.status_code, 200)
        self.assertIsNone(res_plan_b_latest.get_json()["plan"])

    def test_database_migration_preserves_existing_data(self):
        """Test that safe migration preserves existing data created before multi-tenancy was added and is idempotent."""
        from backend.database.db import migrate_db_schema, init_db

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Verify users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        self.assertIsNotNone(cursor.fetchone())

        # Insert a pre-existing legacy subject with user_id NULL
        cursor.execute(
            """
            INSERT INTO subjects (user_id, name, difficulty_level, target_grade, exam_date, syllabus_units_total, units_completed)
            VALUES (NULL, 'Legacy Computer Science', 'hard', 'A', '2026-12-01', 5, 2)
            """
        )
        conn.commit()

        # Verify row exists in DB
        cursor.execute("SELECT * FROM subjects WHERE name = 'Legacy Computer Science'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Legacy Computer Science")
        self.assertIsNone(row["user_id"])

        # Execute migration repeatedly (idempotency check)
        migrate_db_schema(conn)
        migrate_db_schema(conn)

        # Confirm data is still intact
        cursor.execute("SELECT * FROM subjects WHERE name = 'Legacy Computer Science'")
        row_after = cursor.fetchone()
        self.assertIsNotNone(row_after)
        self.assertEqual(row_after["name"], "Legacy Computer Science")
        conn.close()

    def test_complete_user_lifecycle_and_features(self):
        """End-to-End Test for the 10-step full workflow requested in section 5."""
        client = self.app.test_client()

        # 1. Register a user and log in
        res_reg = client.post("/api/auth/register", json={
            "name": "E2E Student",
            "email": "e2e@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!"
        })
        self.assertEqual(res_reg.status_code, 201)

        # 2. Create a subject and confirm it appears in the subject list
        future_date = (datetime.now().date() + timedelta(days=10)).isoformat()
        res_sub = client.post("/api/subjects", json={
            "name": "Machine Learning",
            "difficulty_level": "hard",
            "target_grade": "A",
            "exam_date": future_date,
            "syllabus_units_total": 6,
            "units_completed": 2
        })
        self.assertEqual(res_sub.status_code, 201)
        sub_id = res_sub.get_json()["subject"]["id"]

        res_list = client.get("/api/subjects")
        self.assertEqual(res_list.status_code, 200)
        subs = res_list.get_json()["subjects"]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["name"], "Machine Learning")

        # 3. Generate a study plan and confirm sessions are saved
        res_plan = client.post("/api/ai/plan", json={"save": True})
        self.assertEqual(res_plan.status_code, 200)
        plan_id = res_plan.get_json()["plan_id"]
        self.assertIsNotNone(plan_id)
        plan_items = res_plan.get_json()["plan_items"]
        self.assertGreater(len(plan_items), 0)

        # 4. Confirm timetable/latest plan and AI insights show the generated plan
        res_latest = client.get("/api/ai/plan/latest")
        self.assertEqual(res_latest.status_code, 200)
        self.assertEqual(res_latest.get_json()["plan"]["id"], plan_id)

        res_explain = client.get(f"/api/ai/explain/{plan_id}")
        self.assertEqual(res_explain.status_code, 200)
        self.assertGreaterEqual(res_explain.get_json()["count"], 1)

        # 5. Check exam-goal feasibility
        res_goals = client.post("/api/ai/goals", json={})
        self.assertEqual(res_goals.status_code, 200)
        goal_results = res_goals.get_json()["goal_results"]
        self.assertEqual(len(goal_results), 1)
        self.assertEqual(goal_results[0]["subject_name"], "Machine Learning")

        # 6. Complete a task and confirm progress updates
        first_item_id = plan_items[0]["id"]
        res_complete = client.patch(f"/api/ai/plan/items/{first_item_id}/complete", json={"is_completed": 1})
        self.assertEqual(res_complete.status_code, 200)
        self.assertEqual(res_complete.get_json()["item"]["is_completed"], 1)

        # 7. Confirm analytics / latest plan uses the correct stored data
        res_latest_after = client.get("/api/ai/plan/latest")
        plan_data = res_latest_after.get_json()["plan"]
        self.assertEqual(plan_data["completed_sessions"], 1)
        self.assertGreater(plan_data["completed_minutes"], 0)

        # 8. Confirm preferences persist
        res_pref_update = client.put("/api/preferences", json={
            "daily_available_hours": 5.5,
            "fatigue_level": "low"
        })
        self.assertEqual(res_pref_update.status_code, 200)

        res_pref_get = client.get("/api/preferences")
        self.assertEqual(res_pref_get.status_code, 200)
        self.assertEqual(res_pref_get.get_json()["preferences"]["daily_available_hours"], 5.5)
        self.assertEqual(res_pref_get.get_json()["preferences"]["fatigue_level"], "low")

        # 9. Confirm a second user cannot access or modify the first user's data
        client2 = self.app.test_client()
        client2.post("/api/auth/register", json={
            "name": "Second User",
            "email": "user2@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!"
        })

        # Cannot see user 1 subject
        res_u2_subs = client2.get("/api/subjects")
        self.assertEqual(len(res_u2_subs.get_json()["subjects"]), 0)

        # Cannot access user 1 subject by ID
        self.assertEqual(client2.get(f"/api/subjects/{sub_id}").status_code, 404)
        # Cannot access user 1 plan by ID
        self.assertEqual(client2.get(f"/api/ai/plan/{plan_id}").status_code, 404)
        # Cannot toggle user 1 task completion
        self.assertEqual(client2.patch(f"/api/ai/plan/items/{first_item_id}/complete", json={"is_completed": 0}).status_code, 404)

        # 10. Confirm logged-out API requests return JSON errors and cannot access private data
        client.post("/api/auth/logout")
        res_unauth = client.get("/api/subjects")
        self.assertEqual(res_unauth.status_code, 401)
        self.assertEqual(res_unauth.content_type, "application/json")
        self.assertFalse(res_unauth.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
