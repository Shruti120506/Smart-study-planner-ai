"""
Integration tests for student study preferences using unittest.TestCase
"""

import os
import sys
import tempfile
import unittest
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


class PreferencesTestCase(unittest.TestCase):
    """Test suite for /api/preferences endpoints."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_get_default_preferences(self):
        """Test retrieving initial default preferences."""
        response = self.client.get("/api/preferences")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        prefs = data["preferences"]
        self.assertEqual(prefs["daily_available_hours"], 4.0)
        self.assertEqual(prefs["fatigue_level"], "medium")
        self.assertEqual(prefs["preferred_time_of_day"], "morning")
        self.assertEqual(prefs["focus_span_minutes"], 45)

    def test_update_preferences_success(self):
        """Test updating preferences with valid payload."""
        payload = {
            "daily_available_hours": 6.5,
            "fatigue_level": "high",
            "preferred_time_of_day": "night",
            "focus_span_minutes": 25
        }
        response = self.client.put("/api/preferences", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        updated = data["preferences"]
        self.assertEqual(updated["daily_available_hours"], 6.5)
        self.assertEqual(updated["fatigue_level"], "high")
        self.assertEqual(updated["preferred_time_of_day"], "night")
        self.assertEqual(updated["focus_span_minutes"], 25)

    def test_update_preferences_validation_errors(self):
        """Test that invalid preference inputs are rejected."""
        # Negative hours
        res_neg = self.client.put("/api/preferences", json={"daily_available_hours": -2.0})
        self.assertEqual(res_neg.status_code, 400)
        self.assertTrue(any("between 0.5 and 16.0" in m for m in res_neg.get_json()["error"]["messages"]))

        # Invalid fatigue level
        res_fatigue = self.client.put("/api/preferences", json={"fatigue_level": "hyper_energetic"})
        self.assertEqual(res_fatigue.status_code, 400)
        self.assertTrue(any("must be 'low', 'medium', or 'high'" in m for m in res_fatigue.get_json()["error"]["messages"]))


if __name__ == "__main__":
    unittest.main()
