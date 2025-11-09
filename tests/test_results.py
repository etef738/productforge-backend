"""
Tests for result service and routes.
"""
import pytest
from services.result_service import ResultService
from models.results_models import EnhancedResult


def test_save_result():
    """Test saving a result."""
    service = ResultService()
    
    result = EnhancedResult(
        job_id="test_job_123",
        agent="test_agent",
        role="Test",
        status="completed",
        output="Test output"
    )
    
    saved = service.save_result(result)
    assert saved.job_id == "test_job_123"


def test_get_result():
    """Test retrieving a result."""
    service = ResultService()
    
    # Create result first
    result = EnhancedResult(
        job_id="test_get_123",
        agent="test_agent",
        role="Test",
        status="completed"
    )
    service.save_result(result)
    
    # Retrieve result
    retrieved = service.get_result("test_get_123")
    assert retrieved is not None
    assert retrieved.job_id == "test_get_123"


def test_list_results():
    """Test listing results."""
    service = ResultService()
    results = service.list_results(limit=10)
    assert isinstance(results, list)


def test_count_results():
    """Test counting results."""
    service = ResultService()
    count = service.count_results()
    assert isinstance(count, int)
    assert count >= 0
