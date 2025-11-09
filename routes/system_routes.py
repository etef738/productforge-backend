"""
System health and status routes.
"""
import time
from functools import lru_cache
from fastapi import APIRouter
from core.redis_client import ping_redis, get_redis_client
from core.openai_client import validate_openai_key
from core.utils import get_log_dir, calculate_uptime
from services.deploy_check_service import DeployCheckService
from datetime import datetime
from core.metrics import get_metrics
import os

router = APIRouter(prefix="/system", tags=["System"])

# Track backend startup time
BACKEND_START_TIME = time.time()


@router.get("/ping")
async def ping():
    """Ping endpoint to check if system is alive."""
    return {"status": "ok", "module": "system", "timestamp": datetime.now().isoformat()}


@lru_cache(maxsize=1)
def _cached_health_snapshot() -> dict:
    """Cached snapshot of system health (5s TTL managed by manual invalidation)."""
    redis_client = get_redis_client()
    redis_connected = ping_redis()
    active_jobs = redis_client.llen("queue")
    for queue in ["queue_high", "queue_low"]:
        active_jobs += redis_client.llen(queue)
    # Use index cardinality for results count for speed
    try:
        total_results = int(redis_client.zcard("results_index"))
    except Exception:
        total_results = 0
    uptime = calculate_uptime(BACKEND_START_TIME)
    return {
        "status": "ok",
        "uptime_seconds": uptime["seconds"],
        "uptime_human": uptime["human"],
        "redis_connected": redis_connected,
        "active_jobs": active_jobs,
        "total_results": total_results,
        "timestamp": datetime.now().isoformat(),
        "version": "Enterprise Refactor v2.0"
    }

_last_health_ts: float = 0.0


@router.get("/health")
async def system_health():
    """Enhanced system health check with uptime and Redis status.
    Cached for 5 seconds to reduce Redis load.
    """
    global _last_health_ts
    now = time.time()
    metrics = get_metrics()
    metrics.increment_system_health_request()
    is_cache_hit = now - _last_health_ts <= 5 and _last_health_ts != 0
    if now - _last_health_ts > 5:
        # Invalidate cache by clearing lru
        try:
            _cached_health_snapshot.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        _last_health_ts = now
    try:
        if is_cache_hit:
            metrics.increment_system_health_cache_hit()
        return _cached_health_snapshot()
    except Exception as e:
        uptime = calculate_uptime(BACKEND_START_TIME)
        return {
            "status": "error",
            "uptime_seconds": uptime["seconds"],
            "redis_connected": False,
            "active_jobs": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/status")
async def system_status():
    """Return current system health indicators for dashboard."""
    redis_client = get_redis_client()
    
    status = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "redis_connected": False,
        "openai_key_active": False,
        "worker_log_active": False,
        "worker_alive": False,
    }
    
    # Check Redis connection
    try:
        status["redis_connected"] = ping_redis()
    except Exception:
        status["redis_connected"] = False
    
    # Check OpenAI key validity
    status["openai_key_active"] = validate_openai_key()
    
    # Check worker log file existence
    log_dir = get_log_dir()
    log_path = os.path.join(log_dir, "worker_log.txt")
    status["worker_log_active"] = os.path.exists(log_path)
    
    # Check if worker is alive via Redis queue heartbeat
    try:
        heartbeat_key = "worker:heartbeat"
        last_heartbeat = redis_client.get(heartbeat_key)
        if last_heartbeat:
            status["worker_alive"] = True
    except Exception:
        status["worker_alive"] = False
    
    return status

@router.get("/verify")
async def verify_deployment():
    """Comprehensive deployment verification for Railway health checks.
    
    Verifies:
    - Redis connectivity and latency
    - OpenAI API key configuration
    - Environment variables
    - File system access
    
    Returns:
        JSON summary of all verification checks
    """
    service = DeployCheckService()
    raw = await service.verify_startup()
    checks = raw.get("checks", {})
    # Derive summary fields
    redis_ok = (checks.get("redis", {}).get("status") == "ok")
    openai_ok = (checks.get("openai", {}).get("status") == "ok") and checks.get("openai", {}).get("configured", False)
    env = checks.get("environment", {})
    env_vars_count = sum(1 for v in env.values() if v == "set")
    templates_count = checks.get("filesystem", {}).get("templates", 0)
    # Uptime from local tracker
    uptime_seconds = int(time.time() - BACKEND_START_TIME)
    return {
        "redis_ok": redis_ok,
        "openai_ok": openai_ok,
        "env_vars_count": env_vars_count,
        "templates_count": templates_count,
        "uptime": uptime_seconds,
        "app_version": "2.0.0",
        "status": raw.get("status", "unknown"),
        "warnings": raw.get("warnings", []),
    }
