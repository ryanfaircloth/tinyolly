"""Tests for health endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    """Test main health endpoint."""
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data


def test_health_db():
    """Test database health endpoint."""
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    # Initially false since DB not configured
    assert data["connected"] is False


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ollyscale-frontend"
    assert "version" in data
    assert "docs" in data
