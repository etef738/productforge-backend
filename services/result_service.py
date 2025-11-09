"""
Result service for managing task results and exports.
Implements indexed retrieval and streaming exports.
"""
import json
from io import StringIO
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi.responses import StreamingResponse
from core.redis_client import (
    get_redis_client,
    store_result as redis_store_result,
    get_result as redis_get_result,
    list_results as redis_list_results,
    list_results_by_workflow,
    list_results_by_agent as redis_list_results_by_agent,
)
from core.utils import sanitize_filename
from models.results_models import EnhancedResult


class ResultService:
    """Service for result management operations."""
    
    def __init__(self):
        self.redis = get_redis_client()
    
    def save_result(self, result: EnhancedResult, ttl: int = 3600) -> EnhancedResult:
        """Save a result to Redis with index update and optional TTL."""
        payload = result.model_dump()
        if not payload.get("timestamp"):
            payload["timestamp"] = datetime.utcnow().isoformat()
        redis_store_result(result.job_id, payload, ttl=ttl)
        return EnhancedResult(**payload)
    
    def get_result(self, job_id: str) -> Optional[EnhancedResult]:
        """Get a result by job ID."""
        data = redis_get_result(job_id)
        return EnhancedResult(**data) if data else None
    
    def list_results(self, limit: int = 10) -> List[EnhancedResult]:
        """List all results, sorted by timestamp."""
        raw = redis_list_results(limit)
        return [EnhancedResult(**r) for r in raw]
    
    def get_results_by_workflow(self, workflow_id: str) -> List[EnhancedResult]:
        """Get all results for a specific workflow."""
        raw = list_results_by_workflow(workflow_id)
        return [EnhancedResult(**r) for r in raw]
    
    def get_results_by_agent(self, agent_name: str, limit: int = 10) -> List[EnhancedResult]:
        """Get all results for a specific agent."""
        raw = redis_list_results_by_agent(agent_name, limit)
        return [EnhancedResult(**r) for r in raw]
    
    def count_results(self) -> int:
        """Count total number of results."""
        # Approximate via index cardinality
        return int(self.redis.zcard("results_index"))

    # ----------------------------
    # Exports (streaming)
    # ----------------------------

    def export_json_stream(self) -> StreamingResponse:
        """Stream JSON export with task name in filename."""
        results = [r.model_dump() for r in self.list_results(limit=1000)]
        task_name = self._latest_task_name(results)
        filename = f"ProductForge_{sanitize_filename(task_name)}.json"

        def generate():
            yield "{""task"": "
            yield json.dumps(task_name)
            yield ", ""results"": ["
            first = True
            for r in results:
                if not first:
                    yield ","
                else:
                    first = False
                yield json.dumps(r)
            yield "]}"

        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        return StreamingResponse(generate(), media_type="application/json", headers=headers)

    def export_txt_stream(self) -> StreamingResponse:
        """Stream TXT/Markdown export with human-readable results."""
        results = [r.model_dump() for r in self.list_results(limit=1000)]
        task_name = self._latest_task_name(results)
        filename = f"ProductForge_{sanitize_filename(task_name)}.txt"

        def generate():
            yield f"## Task: {task_name}\n\n"  # noqa: E231
            yield "# 🧠 ProductForge AI Agent Results\n\n"
            for res in results:
                job = res.get("job", "Unknown Task")
                output = res.get("output", "No output available.")
                yield f"## 🧩 Task:\n{job}\n\n"
                yield f"### 💡 Result:\n{output}\n\n"
                yield f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"

        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        return StreamingResponse(generate(), media_type="text/plain", headers=headers)

    def export_performance(self, fmt: str = "json") -> StreamingResponse:
        """Export aggregated agent performance metrics in JSON or CSV."""
        metrics = self._aggregate_performance()
        if fmt.lower() == "csv":
            # CSV header uses keys of first metrics entry
            headers = [
                "agent_name","role","total_tasks","successful_tasks","failed_tasks",
                "success_rate","total_execution_time","average_execution_time",
                "fastest_job","slowest_job","last_activity"
            ]

            def generate_csv():
                yield ",".join(headers) + "\n"
                for m in metrics:
                    row = [str(m.get(h, "")) for h in headers]
                    yield ",".join(row) + "\n"

            return StreamingResponse(generate_csv(), media_type="text/csv",
                                      headers={"Content-Disposition": "attachment; filename=agent_performance_metrics.csv"})

        # JSON
        payload = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "total_agents": len(metrics),
            "metrics": metrics,
        }

        def generate_json():
            yield json.dumps(payload)

        return StreamingResponse(generate_json(), media_type="application/json",
                                  headers={"Content-Disposition": "attachment; filename=agent_performance_metrics.json"})

    # ----------------------------
    # Internals
    # ----------------------------
    def _latest_task_name(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "Unknown_Task"
        latest = sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
        return latest.get("task") or latest.get("job") or "Unknown_Task"

    def _aggregate_performance(self) -> List[Dict[str, Any]]:
        r = get_redis_client()
        # Build agent metrics from agent keys and recent results
        agent_metrics: Dict[str, Dict[str, Any]] = {}

        # Pull agents from index if exists; fallback to key scan
        try:
            agent_names = r.zrevrange("agents_index", 0, -1)
        except Exception:
            agent_names = []

        if not agent_names:
            # minimal fallback
            for key in r.scan_iter("agent:*"):
                agent_names.append(key.split(":", 1)[1])

        # Initialize metrics
        for name in agent_names:
            # Try to read role from agent record
            agent_data_raw = r.get(f"agent:{name}")
            role = "Unknown"
            if agent_data_raw:
                try:
                    role = json.loads(agent_data_raw).get("role", "Unknown")
                except Exception:
                    pass
            agent_metrics[name] = {
                "agent_name": name,
                "role": role,
                "total_tasks": 0,
                "successful_tasks": 0,
                "failed_tasks": 0,
                "success_rate": 0.0,
                "total_execution_time": 0.0,
                "average_execution_time": 0.0,
                "fastest_job": float("inf"),
                "slowest_job": 0.0,
                "last_activity": None,
            }

        # Use indexed results sample
        recent = redis_list_results(1000)
        exec_times: Dict[str, List[float]] = {}
        for res in recent:
            agent_name = res.get("agent") or res.get("agent_name")
            if not agent_name:
                continue
            metrics = agent_metrics.setdefault(agent_name, {
                "agent_name": agent_name,
                "role": res.get("role", "Unknown"),
                "total_tasks": 0,
                "successful_tasks": 0,
                "failed_tasks": 0,
                "success_rate": 0.0,
                "total_execution_time": 0.0,
                "average_execution_time": 0.0,
                "fastest_job": float("inf"),
                "slowest_job": 0.0,
                "last_activity": None,
            })
            metrics["total_tasks"] += 1
            if res.get("output") and res.get("status") != "error":
                metrics["successful_tasks"] += 1
            else:
                metrics["failed_tasks"] += 1
            exec_time = res.get("execution_time") or 0
            if exec_time:
                metrics["total_execution_time"] += exec_time
                metrics["fastest_job"] = min(metrics["fastest_job"], exec_time)
                metrics["slowest_job"] = max(metrics["slowest_job"], exec_time)
                exec_times.setdefault(agent_name, []).append(exec_time)
            ts = res.get("timestamp") or res.get("completed_at")
            if ts and (not metrics["last_activity"] or ts > metrics["last_activity"]):
                metrics["last_activity"] = ts

        # Finalize derived metrics
        out = []
        for name, m in agent_metrics.items():
            if m["total_tasks"] > 0:
                m["success_rate"] = round((m["successful_tasks"] / m["total_tasks"]) * 100, 2)
            times = exec_times.get(name)
            if times:
                m["average_execution_time"] = round(sum(times) / len(times), 2)
            if m["fastest_job"] == float("inf"):
                m["fastest_job"] = 0.0
            else:
                m["fastest_job"] = round(m["fastest_job"], 2)
            m["slowest_job"] = round(m["slowest_job"], 2)
            m["total_execution_time"] = round(m["total_execution_time"], 2)
            out.append(m)
        return out
