"""Orchestration service for managing multi-agent workflows.

This module centralizes orchestration logic that previously lived inside the
monolithic `main.py`. Workflows are stored in Redis using:

Keys
-----
workflow:{workflow_id} : JSON serialized workflow metadata & steps
workflows_index        : Sorted set (score = creation timestamp) of workflow IDs

Each workflow stores an ordered list of step descriptors. Step completion is
derived lazily by inspecting corresponding result:{job_id} keys produced by
downstream workers. This keeps orchestration state consistent without polling
loops or expensive SCAN operations (all lookups are direct key gets and a
ZREVRANGE on the index).
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime

from core.redis_client import get_redis_client
from services.agent_service import AgentService

# Redis key constants
WORKFLOW_KEY_PREFIX = "workflow:"
WORKFLOWS_INDEX = "workflows_index"


class OrchestrationService:
    """Service encapsulating multi‑agent workflow orchestration.

    Responsibilities:
      * Create multi‑step workflows (admin → specialist → QA → admin feedback)
      * Persist workflow metadata and index entries
      * Provide status introspection with derived step progress
      * List recent workflows via sorted set index (O(log n + k))
      * Support admin review spawning new QA jobs post‑hoc
    """

    def __init__(self):
        self.redis = get_redis_client()
        self.agent_service = AgentService()

    # ------------------------------------------------------------------
    # Public API (async for symmetry with FastAPI even though operations
    # are synchronous Redis calls; allows future awaits).
    # ------------------------------------------------------------------
    async def orchestrate_multi_agent(self, task: "TaskRequest") -> Dict[str, Any]:
        """Create a multi-agent workflow with optional QA chain.

        Mirrors legacy /orchestrate behavior from main.py while improving
        storage (uses sorted set index) and documentation.

        Steps generated (when QA enabled):
          1. admin_analysis        (general_assistant)
          2. specialist_execution  (auto-assigned specialist)
          3. qa_validation         (qa_bot)
          4. admin_feedback        (general_assistant)

        Returns a schema-compatible dict used by existing clients.
        """
        workflow_id = str(uuid4())
        created_at = datetime.now().isoformat()

        # Ensure base agents exist
        self.agent_service.create_default_agents()

        # Auto assign specialist based on task description
        specialist = self._auto_assign_agent_sync(task.job)

        steps: List[Dict[str, Any]] = []

        def _enqueue(step: str, agent: str, job_text: str, parent: Optional[str] = None):
            job_id = str(uuid4())
            payload = {
                "job_id": job_id,
                "workflow_id": workflow_id,
                "job": job_text,
                "agent_name": agent,
                "step": step,
                "parent_job_id": parent,
                "created_at": datetime.now().isoformat(),
                "mode": step
            }
            self.redis.lpush("queue", json.dumps(payload))
            steps.append({
                "step": step,
                "agent": agent,
                "job_id": job_id,
                "status": "queued",
                **({"depends_on": parent} if parent else {})
            })
            return job_id

        # Step 1: Admin analysis
        admin_analysis_id = _enqueue(
            "admin_analysis",
            "general_assistant",
            f"Analyze task and produce execution plan: {task.job}"
        )

        # Step 2: Specialist execution
        specialist_id = _enqueue(
            "specialist_execution",
            specialist,
            task.job,
            parent=admin_analysis_id
        )

        if task.requires_qa:
            # Step 3: QA validation
            qa_id = _enqueue(
                "qa_validation",
                "qa_bot",
                f"Review and evaluate specialist output for: {task.job}",
                parent=specialist_id
            )
            # Step 4: Final admin feedback
            _enqueue(
                "admin_feedback",
                "general_assistant",
                f"Provide final summary and recommendations for: {task.job}",
                parent=qa_id
            )

        workflow_doc = {
            "workflow_id": workflow_id,
            "original_task": task.job,
            "steps": steps,
            "status": "running",
            "qa_enabled": bool(task.requires_qa),
            "created_at": created_at
        }

        # Persist workflow + index
        self.redis.set(f"{WORKFLOW_KEY_PREFIX}{workflow_id}", json.dumps(workflow_doc))
        self.redis.zadd(WORKFLOWS_INDEX, {workflow_id: datetime.fromisoformat(created_at).timestamp()})

        return {
            "status": "orchestrated",
            "workflow_id": workflow_id,
            "steps": steps,
            "estimated_completion": "3-8 minutes",
            "qa_chain_enabled": bool(task.requires_qa)
        }

    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Retrieve workflow status with live step completion updates.

        This reproduces legacy /workflows/{workflow_id} behavior. Each step is
        updated on-the-fly by checking for corresponding result:{job_id} keys.
        """
        key = f"{WORKFLOW_KEY_PREFIX}{workflow_id}"
        raw = self.redis.get(key)
        if not raw:
            return {"error": "Workflow not found", "workflow_id": workflow_id}

        workflow = json.loads(raw)
        changed = False
        completed_count = 0
        for step in workflow.get("steps", []):
            if step.get("status") == "completed":
                completed_count += 1
                continue
            result_key = f"result:{step['job_id']}"
            res_raw = self.redis.get(result_key)
            if res_raw:
                res = json.loads(res_raw)
                step["status"] = "completed"
                snippet = res.get("output", "")
                if snippet and len(snippet) > 300:
                    snippet = snippet[:300] + "..."
                step["output"] = snippet
                step["execution_time"] = res.get("execution_time")
                step["confidence_score"] = res.get("confidence_score")
                completed_count += 1
                changed = True
            elif step.get("status") == "queued":
                step["status"] = "processing"
                changed = True

        if completed_count == len(workflow.get("steps", [])) and workflow.get("status") != "completed":
            workflow["status"] = "completed"
            workflow["completed_at"] = datetime.now().isoformat()
            changed = True

        if changed:
            self.redis.set(key, json.dumps(workflow))

        return {"workflow": workflow}

    async def list_workflows(self, limit: int = 20) -> Dict[str, Any]:
        """List recent workflows (running + completed) ordered by recency.

        Equivalent to legacy /workflows output while using the sorted set
        index (no SCAN). Returns up to `limit` workflows.
        """
        ids = self.redis.zrevrange(WORKFLOWS_INDEX, 0, limit - 1)
        workflows: List[Dict[str, Any]] = []
        for wid in ids:
            data = self.redis.get(f"{WORKFLOW_KEY_PREFIX}{wid}")
            if data:
                workflows.append(json.loads(data))
        return {
            "total_workflows": len(workflows),
            "active": [w for w in workflows if w.get("status") == "running"],
            "completed": [w for w in workflows if w.get("status") == "completed"]
        }

    async def admin_review(self, job_id: str, review_prompt: str) -> Dict[str, Any]:
        """Spawn an admin/QA review task for an existing result.

        Mimics legacy /admin_review behavior so existing clients get the same
        response contract.
        """
        review_job_id = str(uuid4())
        payload = {
            "job_id": review_job_id,
            "job": f"{review_prompt}\n\nOriginal Job ID: {job_id}",
            "agent_name": "qa_bot",
            "mode": "admin_review",
            "original_job_id": job_id,
            "created_at": datetime.now().isoformat()
        }
        self.redis.lpush("queue", json.dumps(payload))
        return {
            "status": "admin_review_queued",
            "review_job_id": review_job_id,
            "original_job_id": job_id,
            "reviewer": "qa_bot"
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _auto_assign_agent_sync(self, job_description: str) -> str:
        """Simplified sync variant of auto-assignment (keyword heuristics)."""
        agents = self.agent_service.list_agents()
        if not agents:
            self.agent_service.create_default_agents()
            agents = self.agent_service.list_agents()
        text = job_description.lower()
        role_map = [
            ("qa", ["test", "qa", "quality", "validate", "verify"], "qa_bot"),
            ("debug", ["debug", "fix", "error", "bug"], "debugger_bot"),
            ("analyze", ["analyze", "review", "audit", "inspect"], "analyzer_bot"),
        ]
        for _role, keywords, agent_name in role_map:
            if any(k in text for k in keywords):
                return agent_name
        return "general_assistant"


# Local import to avoid circular typing issues
class TaskRequest:  # shadowed at runtime by pydantic model in route layer
    job: str
    requires_qa: bool

