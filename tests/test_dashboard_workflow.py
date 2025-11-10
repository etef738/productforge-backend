"""Phase 7 dashboard workflow integration tests.
Minimal rendering checks to ensure new pages are wired.
"""
from fastapi.testclient import TestClient
from main_refactored import app

client = TestClient(app)


def test_dashboard_overview_renders():
    r = client.get("/dashboard/")
    assert r.status_code == 200
    assert "System Health" in r.text or "ProductForge" in r.text


def test_dashboard_upload_page_renders():
    r = client.get("/dashboard/upload")
    assert r.status_code == 200
    assert "Recent Uploads" in r.text or "Upload" in r.text


def test_dashboard_agents_page_renders():
    r = client.get("/dashboard/agents")
    assert r.status_code == 200
    assert "Agents" in r.text


def test_dashboard_results_page_renders():
    r = client.get("/dashboard/results")
    assert r.status_code == 200
    assert "Results" in r.text


def test_dashboard_workflows_page_contains_form():
    r = client.get("/dashboard/workflows")
    assert r.status_code == 200
    assert "Create Workflow" in r.text
    assert "name=\"job\"" in r.text or "Describe the task" in r.text


def test_reports_page_renders():
    r = client.get("/dashboard/reports")
    assert r.status_code == 200
    assert "Report" in r.text or "Generate" in r.text
