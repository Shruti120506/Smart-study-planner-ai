"""
Integration tests for Subject CRUD operations and validation rules using unittest.TestCase
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
except ImportError:
    from app import create_app


class SubjectsCrudTestCase(unittest.TestCase):
    """Test suite for Subject CRUD endpoints and business rules."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_list_subjects_empty(self):
        """Test retrieving subjects when database is empty."""
        response = self.client.get("/api/subjects")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["subjects"], [])

    def test_create_subject_success(self):
        """Test successfully creating a subject with valid data."""
        future_date = (datetime.now().date() + timedelta(days=10)).isoformat()
        payload = {
            "name": "Artificial Intelligence",
            "difficulty_level": "hard",
            "target_grade": "A",
            "exam_date": future_date,
            "syllabus_units_total": 5,
            "units_completed": 2
        }
        response = self.client.post("/api/subjects", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data["success"])
        sub = data["subject"]
        self.assertEqual(sub["name"], "Artificial Intelligence")
        self.assertEqual(sub["difficulty_level"], "hard")
        self.assertEqual(sub["completion_percentage"], 40.0)
        self.assertEqual(sub["remaining_units"], 3)
        self.assertEqual(sub["days_until_exam"], 10)

    def test_create_duplicate_subject_rejected(self):
        """Test that duplicate subject name is rejected with 409 Conflict."""
        payload = {"name": "Software Engineering", "difficulty_level": "easy"}
        self.client.post("/api/subjects", json=payload)

        # Attempt creating duplicate with different case
        dup_res = self.client.post("/api/subjects", json={"name": "software engineering"})
        self.assertEqual(dup_res.status_code, 409)
        data = dup_res.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "DUPLICATE_SUBJECT")

    def test_validation_empty_name(self):
        """Test that empty subject name is rejected."""
        response = self.client.post("/api/subjects", json={"name": "   "})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(any("name is required" in m for m in data["error"]["messages"]))

    def test_validation_invalid_difficulty(self):
        """Test that invalid difficulty level is rejected."""
        response = self.client.post("/api/subjects", json={"name": "Physics", "difficulty_level": "extreme"})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("difficulty level must be one of" in m.lower() for m in data["error"]["messages"]))

    def test_validation_past_exam_date(self):
        """Test that past exam date is rejected."""
        past_date = (datetime.now().date() - timedelta(days=5)).isoformat()
        response = self.client.post("/api/subjects", json={"name": "History", "exam_date": past_date})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("cannot be in the past" in m.lower() for m in data["error"]["messages"]))

    def test_validation_completed_exceeds_total_units(self):
        """Test that completed units cannot exceed total units."""
        response = self.client.post(
            "/api/subjects",
            json={"name": "Chemistry", "syllabus_units_total": 4, "units_completed": 7}
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("cannot exceed total units" in m.lower() for m in data["error"]["messages"]))

    def test_get_and_update_subject(self):
        """Test retrieving and updating an existing subject."""
        create_res = self.client.post(
            "/api/subjects",
            json={"name": "Discrete Mathematics", "difficulty_level": "hard", "syllabus_units_total": 5, "units_completed": 1}
        )
        sub_id = create_res.get_json()["subject"]["id"]

        # Get by ID
        get_res = self.client.get(f"/api/subjects/{sub_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["subject"]["name"], "Discrete Mathematics")

        # Update units completed
        update_res = self.client.put(f"/api/subjects/{sub_id}", json={"units_completed": 3})
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.get_json()["subject"]
        self.assertEqual(updated["units_completed"], 3)
        self.assertEqual(updated["completion_percentage"], 60.0)
        self.assertEqual(updated["remaining_units"], 2)

    def test_delete_subject(self):
        """Test deleting a subject by ID."""
        create_res = self.client.post("/api/subjects", json={"name": "Biology"})
        sub_id = create_res.get_json()["subject"]["id"]

        del_res = self.client.delete(f"/api/subjects/{sub_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["success"])

        get_res = self.client.get(f"/api/subjects/{sub_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_seed_sample_subjects_endpoint(self):
        """Test the POST /api/subjects/sample endpoint."""
        res = self.client.post("/api/subjects/sample")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["details"]["added_count"], 3)

        list_res = self.client.get("/api/subjects")
        self.assertGreaterEqual(list_res.get_json()["count"], 3)


if __name__ == "__main__":
    unittest.main()
