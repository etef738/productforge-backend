"""Analytics aggregation service.

Computes rolling statistics from Redis indices and metrics, stores a snapshot
in Redis under key 'analytics_snapshot' with TTL of 60 seconds.
"""
from __future__ import annotations

import time
from typing import Dict, Any, List
from datetime import datetime, timedelta, UTC

from core.redis_client import get_redis_client
from core.metrics import get_metrics
from core.logging_config import get_logger

logger = get_logger(__name__)


class AnalyticsService:
    """Service for computing analytics and trend data."""

    def __init__(self):
        self.redis = get_redis_client()
        self.metrics = get_metrics()

    def _zcount_range(self, key: str, start_ts: float, end_ts: float) -> int:
        try:
            return int(self.redis.zcount(key, start_ts, end_ts))
        except Exception:
            return 0

    def _count_list_len(self, key: str) -> int:
        try:
            return int(self.redis.llen(key))
        except Exception:
            return 0

    def _safe_get(self, key: str) -> Any:
        try:
            return self.redis.get(key)
        except Exception:
            return None

    def _active_agents_count(self) -> int:
        # Attempt to read agents set/list; fallback to 0
        try:
            return int(self.redis.scard("agents_index"))
        except Exception:
            return 0

    def compute_snapshot(self) -> Dict[str, Any]:
        now = time.time()
        dt_now = datetime.fromtimestamp(now, UTC)
        one_hour_ago = now - 3600
        one_day_ago = now - 86400
        one_week_ago = now - 7 * 86400

        # Indices: use sorted sets if available, else fallback to counts
        results_key = "results_index"
        workflows_key = "workflows_index"
        uploads_key = "uploads_index"

        # Rolling counts via zcount
        results_1h = self._zcount_range(results_key, one_hour_ago, now)
        results_24h = self._zcount_range(results_key, one_day_ago, now)
        results_7d = self._zcount_range(results_key, one_week_ago, now)

        # Fall back totals using zcard
        try:
            total_results = int(self.redis.zcard(results_key))
        except Exception:
            total_results = 0

        try:
            total_workflows = int(self.redis.zcard(workflows_key))
        except Exception:
            total_workflows = 0

        try:
            total_uploads = int(self.redis.zcard(uploads_key))
        except Exception:
            total_uploads = 0

        # Compute KPIs
        total_tasks_processed = total_results  # proxy
        avg_processing_time_ms = 0.0  # requires per-task durations; placeholder
        active_agents_count = self._active_agents_count()

        # Average Redis latency: use last observed from metrics as proxy
        avg_redis_latency_ms = self.metrics.to_dict().get("redis_latency_ms", 0.0)

        # Cache hit ratio for system health
        m = self.metrics.to_dict()
        hits = m.get("system_health_cache_hits", 0)
        reqs = max(1, m.get("system_health_requests_total", 1))
        cache_hit_ratio = round(float(hits) / float(reqs), 3)

        snapshot = {
            "timestamp": dt_now.isoformat() + "Z",
            "window": {
                "h1": {"tasks": results_1h},
                "h24": {"tasks": results_24h},
                "d7": {"tasks": results_7d},
            },
            "totals": {
                "results": total_results,
                "workflows": total_workflows,
                "uploads": total_uploads,
            },
            "kpis": {
                "total_tasks_processed": total_tasks_processed,
                "avg_processing_time_ms": avg_processing_time_ms,
                "active_agents_count": active_agents_count,
                "avg_redis_latency_ms": avg_redis_latency_ms,
                "cache_hit_ratio": cache_hit_ratio,
            },
        }

        # Store snapshot with TTL = 60 seconds
        try:
            self.redis.set("analytics_snapshot", str(snapshot), ex=60)
            self.metrics.increment_analytics_snapshots()
            logger.info("analytics_snapshot_refreshed")
        except Exception:
            logger.warning("Failed to store analytics_snapshot")

        return snapshot

    def trends_24h(self) -> Dict[str, Any]:
        """Return simple 24h trend data. If indices are missing, return flat series."""
        now = datetime.now(UTC)
        points: List[Dict[str, Any]] = []
        key = "results_index"
        for h in range(24):
            end = now - timedelta(hours=h)
            start = end - timedelta(hours=1)
            start_ts = start.timestamp()
            end_ts = end.timestamp()
            count = self._zcount_range(key, start_ts, end_ts)
            points.append({
                "t": end.strftime("%H:%M"),
                "count": count
            })
        points.reverse()
        return {"series": points}
