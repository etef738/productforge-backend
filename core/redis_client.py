"""Redis client configuration, connection management, and indexed helpers.

Provides higher-level primitives for storing and retrieving agents, results, and
workflows using sorted set indices instead of full key scans for performance.
"""
import os
import time
import json
import redis
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Global Redis connection singleton
_redis_client: Optional[redis.Redis] = None

# Index keys
RESULTS_INDEX = "results_index"           # ZSET: score = timestamp, member = job_id
WORKFLOWS_INDEX = "workflows_index"       # ZSET: score = timestamp, member = workflow_id
AGENTS_INDEX = "agents_index"             # ZSET: score = created_at timestamp, member = agent_name
UPLOADS_INDEX = "uploads_index"           # ZSET: score = upload timestamp, member = upload_id


def _now_ts() -> float:
    return time.time()


def get_redis_client() -> redis.Redis:
    """Return singleton Redis client (decode responses)."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def ping_redis() -> bool:
    try:
        return get_redis_client().ping()
    except Exception:
        return False


# ----------------------------
# Agent Index Helpers
# ----------------------------
def index_agent(agent_name: str, created_at_iso: str) -> None:
    """Add or update agent in agents index."""
    ts = _iso_to_ts(created_at_iso) or _now_ts()
    r = get_redis_client()
    r.zadd(AGENTS_INDEX, {agent_name: ts})


def list_agents_index(limit: int = 50) -> List[str]:
    """List agent names ordered by creation time descending."""
    r = get_redis_client()
    return r.zrevrange(AGENTS_INDEX, 0, limit - 1)


# ----------------------------
# Result Index Helpers
# ----------------------------
def store_result(job_id: str, result_dict: Dict[str, Any], ttl: int = 3600) -> None:
    """Store a result and update time-based index.

    result_dict must include a timestamp (ISO). If missing, it's added.
    """
    r = get_redis_client()
    if "timestamp" not in result_dict:
        result_dict["timestamp"] = datetime.utcnow().isoformat()
    key = f"result:{job_id}"
    r.setex(key, ttl, json.dumps(result_dict))
    ts = _iso_to_ts(result_dict["timestamp"]) or _now_ts()
    r.zadd(RESULTS_INDEX, {job_id: ts})


def get_result(job_id: str) -> Optional[Dict[str, Any]]:
    r = get_redis_client()
    data = r.get(f"result:{job_id}")
    return json.loads(data) if data else None


def list_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Return latest results ordered by timestamp without scanning keys."""
    r = get_redis_client()
    job_ids = r.zrevrange(RESULTS_INDEX, 0, limit - 1)
    out: List[Dict[str, Any]] = []
    pipeline = r.pipeline()
    for jid in job_ids:
        pipeline.get(f"result:{jid}")
    raw_values = pipeline.execute()
    for raw in raw_values:
        if raw:
            out.append(json.loads(raw))
    # Already ordered by zset score desc
    return out


def list_results_by_agent(agent_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Filter results for a given agent efficiently after primary index retrieval."""
    # Pull a larger window then filter in memory (tunable)
    window = max(limit * 5, 50)
    all_recent = list_results(window)
    filtered = [r for r in all_recent if r.get("agent") == agent_name or r.get("agent_name") == agent_name]
    return filtered[:limit]


def list_results_by_workflow(workflow_id: str) -> List[Dict[str, Any]]:
    # Workflow results may span time slices; pull a broader window
    all_recent = list_results(200)
    wf = [r for r in all_recent if r.get("workflow_id") == workflow_id]
    # Sort by started_at or timestamp ascending
    wf.sort(key=lambda x: x.get("started_at") or x.get("timestamp", ""))
    return wf


# ----------------------------
# Workflow Index Helpers
# ----------------------------
def store_workflow(workflow_id: str, workflow_dict: Dict[str, Any], ttl: int = 3600) -> None:
    r = get_redis_client()
    if "created_at" not in workflow_dict:
        workflow_dict["created_at"] = datetime.utcnow().isoformat()
    key = f"workflow:{workflow_id}"
    r.setex(key, ttl, json.dumps(workflow_dict))
    ts = _iso_to_ts(workflow_dict["created_at"]) or _now_ts()
    r.zadd(WORKFLOWS_INDEX, {workflow_id: ts})


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    r = get_redis_client()
    data = r.get(f"workflow:{workflow_id}")
    return json.loads(data) if data else None


def list_workflows(limit: int = 10) -> List[Dict[str, Any]]:
    r = get_redis_client()
    wf_ids = r.zrevrange(WORKFLOWS_INDEX, 0, limit - 1)
    pipeline = r.pipeline()
    for wid in wf_ids:
        pipeline.get(f"workflow:{wid}")
    raw_values = pipeline.execute()
    out: List[Dict[str, Any]] = []
    for raw in raw_values:
        if raw:
            out.append(json.loads(raw))
    return out


# ----------------------------
# Utility
# ----------------------------
def _iso_to_ts(iso_str: str) -> Optional[float]:
    try:
        # Use fromisoformat for speed; fallback minimal
        return datetime.fromisoformat(iso_str.replace("Z", "")).timestamp()
    except Exception:
        return None


# ----------------------------
# Upload Index Helpers
# ----------------------------
def index_upload(upload_id: str, metadata: Dict[str, Any]) -> None:
    """Store an upload metadata record and add it to the uploads index."""
    r = get_redis_client()
    if "uploaded_at" not in metadata:
        metadata["uploaded_at"] = datetime.utcnow().isoformat()
    ts = _iso_to_ts(metadata["uploaded_at"]) or _now_ts()
    key = f"upload:{upload_id}"
    # Store metadata with 7 day TTL
    r.setex(key, 7 * 86400, json.dumps(metadata))
    r.zadd(UPLOADS_INDEX, {upload_id: ts})


def list_uploads(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent uploads from sorted set index (O(log n + k))."""
    r = get_redis_client()
    upload_ids = r.zrevrange(UPLOADS_INDEX, 0, limit - 1)
    pipeline = r.pipeline()
    for uid in upload_ids:
        pipeline.get(f"upload:{uid}")
    raw_values = pipeline.execute()
    out: List[Dict[str, Any]] = []
    for raw in raw_values:
        if raw:
            out.append(json.loads(raw))
    return out


def get_upload(upload_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve upload metadata by ID."""
    r = get_redis_client()
    data = r.get(f"upload:{upload_id}")
    return json.loads(data) if data else None


