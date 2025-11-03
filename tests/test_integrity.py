# Test suite for repository integrity checks
import os
import subprocess
import pytest
from pathlib import Path

class TestRepositoryIntegrity:
    """Test suite to ensure repository maintains structural integrity"""
    
    def test_enhanced_result_unique(self):
        """Ensure EnhancedResult class exists in exactly one location"""
        dupes = subprocess.getoutput("grep -r '^class EnhancedResult' . --include='*.py' --exclude-dir=.venv --exclude-dir=tests | wc -l")
        assert dupes.strip() == "1", f"Expected 1 EnhancedResult class, found {dupes.strip()}"
    
    def test_no_duplicate_classes(self):
        """Ensure no duplicate class definitions exist"""
        result = subprocess.getoutput(
            "grep -r '^class ' . --include='*.py' --exclude-dir=.venv --exclude-dir=.git | "
            "cut -d':' -f2 | sed 's/^[[:space:]]*//' | cut -d'(' -f1 | "
            "sort | uniq -c | awk '$1 > 1 {print $2}'"
        )
        assert result.strip() == "", f"Duplicate classes found: {result.strip()}"
    
    def test_models_file_exists(self):
        """Ensure canonical models.py file exists"""
        models_path = Path("models.py")
        assert models_path.exists(), "models.py file must exist"
        assert models_path.is_file(), "models.py must be a file"
    
    def test_core_modules_importable(self):
        """Ensure all core modules can be imported without error"""
        core_modules = ['config', 'models', 'main', 'worker', 'worker_health']
        
        for module in core_modules:
            try:
                __import__(module)
            except ImportError as e:
                pytest.fail(f"Failed to import {module}: {e}")
    
    def test_enhanced_result_import_works(self):
        """Ensure EnhancedResult can be imported from models"""
        try:
            from models import EnhancedResult
            # Test instantiation
            result = EnhancedResult(job_id="test-123")
            assert result.job_id == "test-123"
        except ImportError as e:
            pytest.fail(f"Failed to import EnhancedResult from models: {e}")
        except Exception as e:
            pytest.fail(f"Failed to create EnhancedResult instance: {e}")
    
    def test_no_circular_imports(self):
        """Ensure no circular import dependencies exist"""
        import_test_script = '''
import sys
try:
    import config
    import models  
    import main
    import worker
    import worker_health
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
'''
        
        result = subprocess.run([
            ".venv/bin/python", "-c", import_test_script
        ], capture_output=True, text=True, cwd=".")
        
        assert result.returncode == 0, f"Circular import detected: {result.stderr}"
        assert "SUCCESS" in result.stdout, f"Import test failed: {result.stdout}"
    
    def test_worker_health_paths_portable(self):
        """Ensure worker_health.py uses portable paths"""
        try:
            import worker_health
            # Should not raise exception about missing /app/logs directory
            monitor = worker_health.WorkerHealthMonitor()
            assert hasattr(monitor, 'redis_url')
        except Exception as e:
            pytest.fail(f"worker_health.py path issue: {e}")
    
    def test_log_directory_creation(self):
        """Ensure log directories are created properly"""
        log_dir = Path("workspace/logs")
        assert log_dir.exists(), "workspace/logs directory should exist"
        assert log_dir.is_dir(), "workspace/logs should be a directory"
    
    def test_environment_template_exists(self):
        """Ensure .env.example template exists for deployment"""
        env_template = Path(".env.example")
        assert env_template.exists(), ".env.example template must exist"
        
        # Check it contains required variables
        content = env_template.read_text()
        assert "OPENAI_API_KEY" in content
        assert "REDIS_URL" in content