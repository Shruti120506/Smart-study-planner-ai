"""
Basic sanity tests for Phase 1 endpoints
"""
import pytest
from backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_root_endpoint(client):
    """Test that root endpoint returns 200 and welcome JSON."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "online"
    assert "Smart Study Planner AI" in data["message"]


def test_health_check_endpoint(client):
    """Test that /api/health endpoint returns 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["uptime_status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data
