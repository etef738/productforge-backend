"""Weekly report generation service.

Generates markdown summary combining analytics snapshot and metrics data.
Optionally can convert to PDF if libraries available (placeholder logic).
"""
from __future__ import annotations

import time
import os
from datetime import datetime, UTC
from typing import Dict, Any, List

from services.analytics_service import AnalyticsService
from core.metrics import get_metrics
from core.logging_config import get_logger

logger = get_logger(__name__)

REPORT_DIR = "workspace/reports"

os.makedirs(REPORT_DIR, exist_ok=True)


class ReportService:
    def __init__(self):
        self.analytics = AnalyticsService()
        self.metrics = get_metrics()

    def generate_weekly_report(self) -> Dict[str, Any]:
        """Generate a weekly report markdown file and return file metadata."""
        snapshot = self.analytics.compute_snapshot()
        metrics_dict = self.metrics.to_dict()
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"weekly_report_{ts}.md"
        path = os.path.join(REPORT_DIR, filename)

        content = [
            f"# Weekly Report – {ts}",
            "", "## Summary", "", "### KPIs", "",
            f"- Total Tasks Processed: {snapshot['kpis']['total_tasks_processed']}",
            f"- Active Agents: {snapshot['kpis']['active_agents_count']}",
            f"- Avg Redis Latency (ms): {snapshot['kpis']['avg_redis_latency_ms']}",
            f"- Cache Hit Ratio: {snapshot['kpis']['cache_hit_ratio']}",
            "", "### Metrics", "",
            f"- Uptime Seconds: {metrics_dict['uptime_seconds']}",
            f"- Total Requests: {metrics_dict['total_requests']}",
            f"- Reports Generated Total: {metrics_dict['reports_generated_total']}",
            f"- Analytics Snapshots Total: {metrics_dict['analytics_snapshots_total']}",
            "", "### Windows", "",
            f"- Last 1h Tasks: {snapshot['window']['h1']['tasks']}",
            f"- Last 24h Tasks: {snapshot['window']['h24']['tasks']}",
            f"- Last 7d Tasks: {snapshot['window']['d7']['tasks']}",
            "", "### Totals", "",
            f"- Total Results: {snapshot['totals']['results']}",
            f"- Total Workflows: {snapshot['totals']['workflows']}",
            f"- Total Uploads: {snapshot['totals']['uploads']}",
            "", "---", "Generated automatically by ProductForge Backend."]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        # Increment metrics counter
        self.metrics.increment_reports_generated()
        logger.info("report_generated path=%s", path)

        return {"report_path": path, "filename": filename, "timestamp": ts}

    def list_reports(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for fname in sorted(os.listdir(REPORT_DIR), reverse=True)[:50]:
            if fname.startswith("weekly_report_") and fname.endswith(".md"):
                full = os.path.join(REPORT_DIR, fname)
                entries.append({
                    "filename": fname,
                    "path": full,
                    "size": os.path.getsize(full),
                    "modified": datetime.fromtimestamp(os.path.getmtime(full), UTC).isoformat() + "Z"
                })
        return entries
