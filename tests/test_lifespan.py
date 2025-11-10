"""
Test FastAPI lifespan context manager implementation.

Verifies:
- Startup logs appear correctly (🚀 ProductForge Backend Starting...)
- Metrics initialization (✅ Metrics ready)
- Railway boot verification (✅✅✅ Railway boot OK)
- Shutdown logs appear correctly (👋 ProductForge Backend Shutting Down...)
- Application is functional after startup
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import logging
import io


def test_lifespan_startup_logs(caplog):
    """Verify startup logs are emitted during lifespan startup phase."""
    with caplog.at_level(logging.INFO):
        # Import app with lifespan enabled
        from main_refactored import app
        
        # Create TestClient with lifespan enabled (triggers startup/shutdown)
        with TestClient(app) as client:
            # Verify startup logs
            log_messages = [record.message for record in caplog.records]
            
            # Check critical startup messages
            assert any("🚀 ProductForge Backend Starting..." in msg for msg in log_messages), \
                "Missing startup banner"
            assert any("✅ Metrics ready" in msg for msg in log_messages), \
                "Missing metrics initialization log"
            assert any("Railway boot OK" in msg or "Railway boot DEGRADED" in msg or "Railway boot FAILED" in msg for msg in log_messages), \
                "Missing Railway boot verification log"
            
            # Verify app is functional after startup
            response = client.get("/system/verify")
            assert response.status_code == 200, "App not functional after startup"
            
            # Shutdown happens automatically when exiting context manager


def test_lifespan_shutdown_logs(caplog):
    """Verify shutdown logs are emitted during lifespan shutdown phase."""
    with caplog.at_level(logging.INFO):
        from main_refactored import app
        
        with TestClient(app) as client:
            # Make a request to confirm app is running
            response = client.get("/")
            assert response.status_code == 200
        
        # After exiting context manager, shutdown should have run
        log_messages = [record.message for record in caplog.records]
        assert any("👋 ProductForge Backend Shutting Down..." in msg for msg in log_messages), \
            "Missing shutdown log"


def test_lifespan_metrics_initialized_before_routes():
    """Verify metrics are initialized before any routes are accessed."""
    from main_refactored import app
    
    with TestClient(app) as client:
        # Access metrics endpoint - should work immediately after startup
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "# HELP" in response.text  # Prometheus format


def test_lifespan_deploy_verification_runs():
    """Verify deployment verification runs during startup."""
    with patch('services.deploy_check_service.DeployCheckService.verify_startup') as mock_verify:
        # Mock the verification to return healthy status
        mock_verify.return_value = {
            "status": "healthy",
            "warnings": []
        }
        
        from main_refactored import app
        
        with TestClient(app) as client:
            # Verify deploy check service was called
            mock_verify.assert_called_once()
            
            # Verify app is functional
            response = client.get("/system/status")
            assert response.status_code == 200


def test_lifespan_degraded_boot_logs_warnings(caplog):
    """Verify degraded boot status logs warnings correctly."""
    with patch('services.deploy_check_service.DeployCheckService.verify_startup') as mock_verify:
        # Mock degraded status
        mock_verify.return_value = {
            "status": "degraded",
            "warnings": ["Redis connection slow", "Template directory permissions"]
        }
        
        with caplog.at_level(logging.WARNING):
            from main_refactored import app
            
            with TestClient(app) as client:
                log_messages = [record.message for record in caplog.records]
                
                # Check for degraded status log
                assert any("Railway boot DEGRADED" in msg for msg in log_messages), \
                    "Missing degraded boot log"
                
                # Check for individual warnings
                assert any("Redis connection slow" in msg for msg in log_messages), \
                    "Missing specific warning log"


def test_lifespan_failed_boot_logs_errors(caplog):
    """Verify failed boot status logs errors correctly."""
    with patch('services.deploy_check_service.DeployCheckService.verify_startup') as mock_verify:
        # Mock failed status
        mock_verify.return_value = {
            "status": "failed",
            "warnings": ["Redis unreachable", "OpenAI key invalid"]
        }
        
        with caplog.at_level(logging.ERROR):
            from main_refactored import app
            
            with TestClient(app) as client:
                log_messages = [record.message for record in caplog.records]
                
                # Check for failed boot log
                assert any("Railway boot FAILED" in msg for msg in log_messages), \
                    "Missing failed boot log"


def test_no_deprecation_warnings():
    """Verify no FastAPI on_event deprecation warnings are emitted."""
    import warnings
    
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        from main_refactored import app
        
        with TestClient(app) as client:
            client.get("/")
        
        # Check for deprecation warnings related to on_event
        deprecation_warnings = [
            warning for warning in w 
            if issubclass(warning.category, DeprecationWarning) 
            and "on_event" in str(warning.message)
        ]
        
        assert len(deprecation_warnings) == 0, \
            f"Found {len(deprecation_warnings)} on_event deprecation warnings"
