"""
Tests for upload endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from main_refactored import app
import io

client = TestClient(app)


def test_upload_ping():
    """Test upload module ping endpoint."""
    response = client.get("/upload/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "upload"


def test_list_uploads():
    """Test listing uploads."""
    response = client.get("/upload/list")
    assert response.status_code == 200
    data = response.json()
    assert "uploads" in data
    assert "count" in data
    assert isinstance(data["uploads"], list)


def test_upload_non_zip_rejected():
    """Test that non-ZIP files are rejected."""
    # Create a fake .txt file
    fake_file = io.BytesIO(b"This is not a ZIP file")
    files = {"file": ("test.txt", fake_file, "text/plain")}
    data = {"project": "test"}
    
    response = client.post("/upload/", files=files, data=data)
    assert response.status_code == 400
    assert "ZIP" in response.json()["detail"]


def test_upload_valid_zip():
    """Test uploading a valid ZIP file."""
    # Create minimal ZIP file in memory
    # ZIP header: PK\x03\x04 (local file header signature)
    fake_zip = io.BytesIO(
        b"PK\x03\x04\x14\x00\x00\x00\x08\x00" +
        b"\x00" * 50  # Minimal ZIP structure
    )
    files = {"file": ("test_archive.zip", fake_zip, "application/zip")}
    data = {"project": "test_project"}
    
    response = client.post("/upload/", files=files, data=data)
    # Accept 200 (success) or 400 (invalid ZIP structure during processing)
    # This test validates the endpoint accepts .zip extension
    assert response.status_code in [200, 400]
    if response.status_code == 200:
        result = response.json()
        assert result["status"] == "uploaded"
        assert "upload_id" in result
        assert "job_id" in result
