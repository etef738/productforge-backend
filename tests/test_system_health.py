"""
Tests for system health endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from main_refactored import app

client = TestClient(app)


def test_system_ping():
    """Test system ping endpoint."""
    response = client.get("/system/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "system"


def test_system_health():
    """Test system health endpoint."""
    response = client.get("/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "redis_connected" in data
    assert "total_results" in data
    assert data["version"] == "Enterprise Refactor v2.0"


def test_system_status():
    """Test system status endpoint."""
    response = client.get("/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "redis_connected" in data
    assert "openai_key_active" in data
    assert "timestamp" in data

