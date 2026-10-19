"""
Tests for root and health-check endpoints using unittest.TestCase
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure paths
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(TESTS_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import create_app
except ImportError:
    from app import create_app


class HealthEndpointsTestCase(unittest.TestCase):
    """Test suite for server health and root endpoints."""

    def setUp(self):
        # Create an isolated temporary database for each test
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_root_endpoint(self):
        """Test that root endpoint returns 200 and welcome JSON."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "online")
        self.assertIn("Smart Study Planner AI", data["message"])

    def test_health_check_endpoint(self):
        """Test that /api/health endpoint returns 200 and healthy status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["uptime_status"], "ok")
        self.assertEqual(data["database"], "connected")
        self.assertIn("timestamp", data)


if __name__ == "__main__":
    unittest.main()
