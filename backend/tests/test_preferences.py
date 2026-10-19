"""
Integration tests for Student Preferences endpoints and validation.
"""

import tempfile
from pathlib import Path
import pytest
from backend.app import create_app


@pytest.fixture
def test_client():
    """Configures a fresh Flask test client with an isolated temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = Path(f.name)

    app = create_app({"TESTING": True, "DATABASE": str(temp_db_path)})
    with app.test_client() as client:
        yield client

    if temp_db_path.exists():
        temp_db_path.unlink()


def test_get_default_preferences(test_client):
    """Test retrieving initial default preferences."""
    response = test_client.get("/api/preferences")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    prefs = data["preferences"]
    assert prefs["daily_available_hours"] == 4.0
    assert prefs["fatigue_level"] == "medium"
    assert prefs["preferred_time_of_day"] == "morning"
    assert prefs["focus_span_minutes"] == 45


def test_update_preferences_success(test_client):
    """Test updating study preferences with valid values."""
    payload = {
        "daily_available_hours": 6.5,
        "fatigue_level": "high",
        "preferred_time_of_day": "night",
        "focus_span_minutes": 25
    }
    response = test_client.put("/api/preferences", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    updated = data["preferences"]
    assert updated["daily_available_hours"] == 6.5
    assert updated["fatigue_level"] == "high"
    assert updated["preferred_time_of_day"] == "night"
    assert updated["focus_span_minutes"] == 25


def test_update_preferences_validation_error(test_client):
    """Test that invalid preference inputs are rejected."""
    # Test negative hours
    res_neg = test_client.put("/api/preferences", json={"daily_available_hours": -2.0})
    assert res_neg.status_code == 400
    assert any("between 0.5 and 16.0" in msg for msg in res_neg.get_json()["error"]["messages"])

    # Test invalid fatigue level
    res_fatigue = test_client.put("/api/preferences", json={"fatigue_level": "exhausted_beyond_belief"})
    assert res_fatigue.status_code == 400
    assert any("must be 'low', 'medium', or 'high'" in msg for msg in res_fatigue.get_json()["error"]["messages"])
