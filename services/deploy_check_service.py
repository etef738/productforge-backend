"""Deployment verification service for Railway health checks.

Provides automated startup verification to ensure all critical services
are available before accepting traffic.
"""
import time
from typing import Dict, Any
from core.redis_client import get_redis_client, ping_redis
from core.openai_client import validate_openai_key
from core.logging_config import get_logger
import os

logger = get_logger(__name__)


class DeployCheckService:
    """Service for verifying deployment health and readiness."""
    
    async def verify_startup(self) -> Dict[str, Any]:
        """Perform comprehensive startup verification.
        
        Checks:
        - Redis connectivity and latency
        - OpenAI API key validity
        - Environment variable presence
        - File system accessibility
        
        Returns:
            Dictionary with verification results and status
        """
        results = {
            "status": "healthy",
            "checks": {},
            "warnings": [],
            "timestamp": time.time()
        }
        
        # Check 1: Redis connectivity
        try:
            start = time.time()
            redis_ok = ping_redis()
            latency_ms = (time.time() - start) * 1000
            
            results["checks"]["redis"] = {
                "status": "ok" if redis_ok else "failed",
                "latency_ms": round(latency_ms, 2),
                "url": os.environ.get("REDIS_URL", "not_set")[:20] + "..."
            }
            
            if not redis_ok:
                results["status"] = "degraded"
                results["warnings"].append("Redis connection failed")
            
            logger.info(f"✅ Redis check: {'OK' if redis_ok else 'FAILED'} ({latency_ms:.2f}ms)")
            
        except Exception as e:
            results["checks"]["redis"] = {"status": "error", "error": str(e)}
            results["status"] = "degraded"
            results["warnings"].append(f"Redis error: {str(e)}")
            logger.error(f"❌ Redis check failed: {e}")
        
        # Check 2: OpenAI API key
        try:
            openai_valid = validate_openai_key()
            results["checks"]["openai"] = {
                "status": "ok" if openai_valid else "missing",
                "configured": openai_valid
            }
            
            if not openai_valid:
                results["warnings"].append("OpenAI API key not configured or invalid")
            
            logger.info(f"✅ OpenAI check: {'OK' if openai_valid else 'NOT CONFIGURED'}")
            
        except Exception as e:
            results["checks"]["openai"] = {"status": "error", "error": str(e)}
            results["warnings"].append(f"OpenAI validation error: {str(e)}")
            logger.error(f"❌ OpenAI check failed: {e}")
        
        # Check 3: Environment variables
        required_vars = ["REDIS_URL"]
        optional_vars = ["OPENAI_API_KEY", "API_KEY", "PORT"]
        
        env_status = {}
        for var in required_vars:
            env_status[var] = "set" if os.environ.get(var) else "missing"
            if not os.environ.get(var):
                results["status"] = "unhealthy"
                results["warnings"].append(f"Required env var {var} is missing")
        
        for var in optional_vars:
            env_status[var] = "set" if os.environ.get(var) else "not_set"
        
        results["checks"]["environment"] = env_status
        logger.info(f"✅ Environment vars: {len([v for v in env_status.values() if v == 'set'])}/{len(env_status)} set")
        
        # Check 4: File system (workspace directory)
        try:
            workspace_path = "workspace"
            if not os.path.exists(workspace_path):
                os.makedirs(workspace_path, exist_ok=True)
                logger.info(f"✅ Created workspace directory: {workspace_path}")
            
            # Check templates directory
            templates_path = "workspace/templates"
            if os.path.exists(templates_path):
                template_files = os.listdir(templates_path)
                results["checks"]["filesystem"] = {
                    "status": "ok",
                    "workspace": "exists",
                    "templates": len(template_files)
                }
                logger.info(f"✅ Templates directory: {len(template_files)} files found")
            else:
                results["checks"]["filesystem"] = {
                    "status": "warning",
                    "workspace": "exists",
                    "templates": 0
                }
                results["warnings"].append("Templates directory not found")
                logger.warning("⚠️ Templates directory not found")
                
        except Exception as e:
            results["checks"]["filesystem"] = {"status": "error", "error": str(e)}
            results["warnings"].append(f"Filesystem error: {str(e)}")
            logger.error(f"❌ Filesystem check failed: {e}")
        
        # Final summary
        if results["status"] == "healthy":
            logger.info("✅✅✅ Railway boot OK - All checks passed ✅✅✅")
        elif results["status"] == "degraded":
            logger.warning(f"⚠️ Railway boot DEGRADED - {len(results['warnings'])} warnings")
        else:
            logger.error(f"❌ Railway boot FAILED - {len(results['warnings'])} errors")
        
        return results
    
    async def quick_health_check(self) -> bool:
        """Quick health check for liveness probe.
        
        Returns:
            True if basic health checks pass
        """
        try:
            redis_ok = ping_redis()
            return redis_ok
        except Exception:
            return False
