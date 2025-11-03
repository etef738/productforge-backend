# Tests for data models
import pytest
from models import EnhancedResult
from datetime import datetime

class TestDataModels:
    """Test suite for Pydantic data models"""
    
    def test_enhanced_result_creation(self):
        """Test EnhancedResult can be created with minimal data"""
        result = EnhancedResult(job_id="test-123")
        assert result.job_id == "test-123"
        assert result.status == "completed"  # default value
        assert result.timestamp is not None
    
    def test_enhanced_result_optional_fields(self):
        """Test EnhancedResult optional fields work correctly"""
        result = EnhancedResult(
            job_id="test-456",
            agent="test_agent",
            role="Test",
            output="Test output",
            workflow_id="workflow-123",
            confidence_score=0.95
        )
        
        assert result.job_id == "test-456"
        assert result.agent == "test_agent"
        assert result.role == "Test"
        assert result.output == "Test output"
        assert result.workflow_id == "workflow-123"
        assert result.confidence_score == 0.95
    
    def test_enhanced_result_validation(self):
        """Test EnhancedResult field validation"""
        # Test confidence score validation (0.0 to 1.0)
        with pytest.raises(ValueError):
            EnhancedResult(job_id="test", confidence_score=1.5)
        
        with pytest.raises(ValueError):
            EnhancedResult(job_id="test", confidence_score=-0.1)
    
    def test_enhanced_result_timestamp_format(self):
        """Test EnhancedResult timestamp is in ISO format"""
        result = EnhancedResult(job_id="test-timestamp")
        
        # Should be able to parse as datetime
        try:
            datetime.fromisoformat(result.timestamp)
        except ValueError:
            pytest.fail("Timestamp should be in ISO format")
    
    def test_enhanced_result_serialization(self):
        """Test EnhancedResult can be serialized to dict/JSON"""
        result = EnhancedResult(
            job_id="serialize-test",
            agent="test_agent",
            output="Test output"
        )
        
        # Test dict conversion
        result_dict = result.model_dump()
        assert isinstance(result_dict, dict)
        assert result_dict["job_id"] == "serialize-test"
        
        # Test JSON serialization
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)
        assert "serialize-test" in json_str