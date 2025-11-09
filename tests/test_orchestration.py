"""
Tests for orchestration endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from main_refactored import app

client = TestClient(app)


def test_orchestrate_endpoint():
    """Test workflow orchestration endpoint."""
    payload = {
        "job": "Test task for orchestration",
        "requires_qa": False
    }
    response = client.post("/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "orchestrated"
    assert "workflow_id" in data
    assert "steps" in data
    assert len(data["steps"]) >= 2  # At least admin_analysis + specialist_execution


def test_orchestrate_with_qa():
    """Test workflow orchestration with QA chain enabled."""
    payload = {
        "job": "Complex task requiring QA",
        "requires_qa": True
    }
    response = client.post("/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "orchestrated"
    assert data["qa_chain_enabled"] is True
    assert len(data["steps"]) >= 4  # admin_analysis, specialist, qa_validation, admin_feedback


def test_list_workflows():
    """Test listing workflows."""
    response = client.get("/workflows?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "total_workflows" in data
    assert "active" in data
    assert "completed" in data


def test_workflow_status():
    """Test retrieving workflow status by ID."""
    # First create a workflow
    payload = {"job": "Status test task", "requires_qa": False}
    create_response = client.post("/orchestrate", json=payload)
    workflow_id = create_response.json()["workflow_id"]
    
    # Then fetch its status
    response = client.get(f"/workflows/{workflow_id}")
    assert response.status_code == 200
    data = response.json()
    assert "workflow" in data
    assert data["workflow"]["workflow_id"] == workflow_id
