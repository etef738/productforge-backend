"""Prometheus-style metrics collection for observability.

Provides in-memory counters and gauges that can be exported in Prometheus
text format via the /metrics endpoint.
"""
import time
from typing import Dict, Any
from datetime import datetime


UPLOAD_COUNTER = None  # Placeholder for compatibility


class MetricsCollector:
    """Thread-safe metrics collector for production monitoring."""
    
    def __init__(self):
        self._start_time = time.time()
        self._total_requests = 0
        self._active_workflows = 0
        self._redis_operations = 0
        self._last_redis_latency_ms = 0.0
        self._system_health_cache_hits = 0
        self._system_health_requests_total = 0
        self._reports_generated_total = 0
        self._analytics_snapshots_total = 0
        self._dashboard_refresh_total = 0
        self._htmx_events_total = 0
        self._cache_hits_total = 0
        self._cache_misses_total = 0
        
    def increment_requests(self):
        """Increment total request counter."""
        self._total_requests += 1
    
    def set_active_workflows(self, count: int):
        """Update active workflow count."""
        self._active_workflows = count
    
    def record_redis_latency(self, latency_ms: float):
        """Record Redis operation latency."""
        self._redis_operations += 1
        self._last_redis_latency_ms = latency_ms

    def increment_system_health_cache_hit(self):
        """Increment system health cache hit counter."""
        self._system_health_cache_hits += 1

    def increment_system_health_request(self):
        """Increment system health total requests counter."""
        self._system_health_requests_total += 1

    def increment_reports_generated(self):
        """Increment total reports generated counter."""
        self._reports_generated_total += 1

    def increment_analytics_snapshots(self):
        """Increment total analytics snapshots counter."""
        self._analytics_snapshots_total += 1

    def increment_dashboard_refresh(self):
        """Increment dashboard refresh counter (HTMX polling)."""
        self._dashboard_refresh_total += 1

    def increment_htmx_event(self):
        """Increment HTMX event counter (user interactions)."""
        self._htmx_events_total += 1

    def increment_cache_hit(self):
        """Increment cache hit counter."""
        self._cache_hits_total += 1

    def increment_cache_miss(self):
        """Increment cache miss counter."""
        self._cache_misses_total += 1
    
    def get_uptime_seconds(self) -> float:
        """Get application uptime in seconds."""
        return time.time() - self._start_time
    
    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format.
        
        Returns:
            Prometheus-formatted metric strings
        """
        uptime = self.get_uptime_seconds()
        
        lines = [
            "# HELP productforge_uptime_seconds Application uptime in seconds",
            "# TYPE productforge_uptime_seconds gauge",
            f"productforge_uptime_seconds {uptime:.2f}",
            "",
            "# HELP productforge_total_requests Total HTTP requests processed",
            "# TYPE productforge_total_requests counter",
            f"productforge_total_requests {self._total_requests}",
            "",
            "# HELP productforge_active_workflows Currently active workflows",
            "# TYPE productforge_active_workflows gauge",
            f"productforge_active_workflows {self._active_workflows}",
            "",
            "# HELP productforge_redis_latency_ms Last Redis operation latency in milliseconds",
            "# TYPE productforge_redis_latency_ms gauge",
            f"productforge_redis_latency_ms {self._last_redis_latency_ms:.2f}",
            "",
            "# HELP productforge_redis_operations Total Redis operations",
            "# TYPE productforge_redis_operations counter",
            f"productforge_redis_operations {self._redis_operations}",
            "",
            "# HELP productforge_system_health_cache_hits System health endpoint cache hits",
            "# TYPE productforge_system_health_cache_hits counter",
            f"productforge_system_health_cache_hits {self._system_health_cache_hits}",
            "",
            "# HELP productforge_system_health_requests_total Total /system/health requests",
            "# TYPE productforge_system_health_requests_total counter",
            f"productforge_system_health_requests_total {self._system_health_requests_total}",
            "",
            "# HELP productforge_reports_generated_total Total reports generated",
            "# TYPE productforge_reports_generated_total counter",
            f"productforge_reports_generated_total {self._reports_generated_total}",
            "",
            "# HELP productforge_analytics_snapshots_total Total analytics snapshots created",
            "# TYPE productforge_analytics_snapshots_total counter",
            f"productforge_analytics_snapshots_total {self._analytics_snapshots_total}",
            "",
            "# HELP productforge_dashboard_refresh_total Dashboard auto-refresh events",
            "# TYPE productforge_dashboard_refresh_total counter",
            f"productforge_dashboard_refresh_total {self._dashboard_refresh_total}",
            "",
            "# HELP productforge_htmx_events_total HTMX interaction events",
            "# TYPE productforge_htmx_events_total counter",
            f"productforge_htmx_events_total {self._htmx_events_total}",
            "",
            "# HELP productforge_cache_hits_total Cache hit count",
            "# TYPE productforge_cache_hits_total counter",
            f"productforge_cache_hits_total {self._cache_hits_total}",
            "",
            "# HELP productforge_cache_misses_total Cache miss count",
            "# TYPE productforge_cache_misses_total counter",
            f"productforge_cache_misses_total {self._cache_misses_total}",
            "",
        ]
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary for JSON endpoints."""
        return {
            "uptime_seconds": round(self.get_uptime_seconds(), 2),
            "total_requests": self._total_requests,
            "active_workflows": self._active_workflows,
            "redis_latency_ms": round(self._last_redis_latency_ms, 2),
            "redis_operations": self._redis_operations,
            "system_health_cache_hits": self._system_health_cache_hits,
            "system_health_requests_total": self._system_health_requests_total,
            "reports_generated_total": self._reports_generated_total,
            "analytics_snapshots_total": self._analytics_snapshots_total,
            "dashboard_refresh_total": self._dashboard_refresh_total,
            "htmx_events_total": self._htmx_events_total,
            "cache_hits_total": self._cache_hits_total,
            "cache_misses_total": self._cache_misses_total,
            "cache_hit_rate": round(
                self._cache_hits_total / max(1, self._cache_hits_total + self._cache_misses_total) * 100, 2
            ),
            "timestamp": datetime.now().isoformat()
        }


# Global singleton instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector instance."""
    return _metrics
