"""
Integration tests for Subject CRUD operations and validation rules.
"""

from datetime import datetime, timedelta
import tempfile
from pathlib import Path
import pytest
try:
    from backend.app import create_app
except ImportError:
    from app import create_app


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


def test_list_subjects_empty(test_client):
    """Test retrieving subjects when no subjects are enrolled."""
    response = test_client.get("/api/subjects")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["count"] == 0
    assert data["subjects"] == []


def test_create_subject_success(test_client):
    """Test creating a valid subject."""
    future_date = (datetime.now().date() + timedelta(days=10)).isoformat()
    payload = {
        "name": "Artificial Intelligence",
        "difficulty_level": "hard",
        "target_grade": "A",
        "exam_date": future_date,
        "syllabus_units_total": 5,
        "units_completed": 2
    }
    response = test_client.post("/api/subjects", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["subject"]["name"] == "Artificial Intelligence"
    assert data["subject"]["difficulty_level"] == "hard"
    assert data["subject"]["completion_percentage"] == 40.0
    assert data["subject"]["remaining_units"] == 3
    assert data["subject"]["days_until_exam"] == 10


def test_create_duplicate_subject_rejected(test_client):
    """Test that creating a subject with existing name returns 409 Conflict."""
    payload = {"name": "Software Engineering", "difficulty_level": "easy"}
    test_client.post("/api/subjects", json=payload)

    # Attempt duplicate (case-insensitive)
    duplicate_res = test_client.post("/api/subjects", json={"name": "software engineering"})
    assert duplicate_res.status_code == 409
    data = duplicate_res.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "DUPLICATE_SUBJECT"


def test_validation_empty_name(test_client):
    """Test that missing or empty subject name returns 400 Bad Request."""
    response = test_client.post("/api/subjects", json={"name": "   "})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert any("name is required" in msg for msg in data["error"]["messages"])


def test_validation_invalid_difficulty(test_client):
    """Test that invalid difficulty level is rejected."""
    response = test_client.post("/api/subjects", json={"name": "Physics", "difficulty_level": "impossible"})
    assert response.status_code == 400
    data = response.get_json()
    assert any("difficulty level must be one of" in msg.lower() for msg in data["error"]["messages"])


def test_validation_past_exam_date(test_client):
    """Test that exam date in the past is rejected."""
    past_date = (datetime.now().date() - timedelta(days=5)).isoformat()
    response = test_client.post("/api/subjects", json={"name": "History", "exam_date": past_date})
    assert response.status_code == 400
    data = response.get_json()
    assert any("cannot be in the past" in msg.lower() for msg in data["error"]["messages"])


def test_validation_completed_exceeds_total_units(test_client):
    """Test that units completed cannot exceed total units."""
    response = test_client.post(
        "/api/subjects",
        json={"name": "Chemistry", "syllabus_units_total": 4, "units_completed": 7}
    )
    assert response.status_code == 400
    data = response.get_json()
    assert any("cannot exceed total units" in msg.lower() for msg in data["error"]["messages"])


def test_get_and_update_subject(test_client):
    """Test retrieving and updating an existing subject."""
    create_res = test_client.post(
        "/api/subjects",
        json={"name": "Discrete Mathematics", "difficulty_level": "hard", "syllabus_units_total": 5, "units_completed": 1}
    )
    sub_id = create_res.get_json()["subject"]["id"]

    # Get single subject
    get_res = test_client.get(f"/api/subjects/{sub_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["subject"]["name"] == "Discrete Mathematics"

    # Update progress
    update_res = test_client.put(
        f"/api/subjects/{sub_id}",
        json={"units_completed": 3}
    )
    assert update_res.status_code == 200
    updated = update_res.get_json()["subject"]
    assert updated["units_completed"] == 3
    assert updated["completion_percentage"] == 60.0
    assert updated["remaining_units"] == 2


def test_delete_subject(test_client):
    """Test deleting a subject by ID."""
    create_res = test_client.post("/api/subjects", json={"name": "Biology"})
    sub_id = create_res.get_json()["subject"]["id"]

    # Delete
    del_res = test_client.delete(f"/api/subjects/{sub_id}")
    assert del_res.status_code == 200
    assert del_res.get_json()["success"] is True

    # Verify not found afterwards
    get_res = test_client.get(f"/api/subjects/{sub_id}")
    assert get_res.status_code == 404


def test_seed_sample_subjects_endpoint(test_client):
    """Test the POST /api/subjects/sample endpoint."""
    res = test_client.post("/api/subjects/sample")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["details"]["added_count"] >= 3

    # List subjects confirms they appear
    list_res = test_client.get("/api/subjects")
    assert list_res.get_json()["count"] >= 3
