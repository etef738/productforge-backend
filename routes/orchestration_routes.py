"""Workflow orchestration routes.

External API Compatibility
--------------------------
These endpoints preserve the legacy surface from `main.py`:
  POST /orchestrate          -> create multi-agent workflow
  GET  /workflows            -> list workflows
  GET  /workflows/{id}       -> workflow status
  POST /admin_review         -> spawn admin/QA review

Internally they delegate entirely to `OrchestrationService` methods.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from services.orchestration_service import OrchestrationService

router = APIRouter(tags=["Orchestration"])


class TaskRequest(BaseModel):
    """Incoming task descriptor for orchestration.

    Fields mirror legacy TaskRequest from monolith to keep clients stable.
    """
    job: str = Field(..., description="Task description to execute")
    agent_name: Optional[str] = Field(None, description="Optional explicit agent")
    priority: Optional[str] = Field("normal", description="Priority: low|normal|high")
    requires_qa: Optional[bool] = Field(False, description="Enable QA chain for workflow")


class AdminReviewRequest(BaseModel):
    job_id: str = Field(..., description="Original job/result ID to review")
    review_prompt: str = Field(
        "Evaluate this output for correctness, completeness, and adherence to requirements.",
        description="Prompt used for admin/QA review"
    )


@router.post("/orchestrate")
async def orchestrate(task: TaskRequest):
    """Create a multi-agent workflow (admin → specialist → optional QA → feedback)."""
    service = OrchestrationService()
    return await service.orchestrate_multi_agent(task)


@router.get("/workflows")
async def list_workflows(limit: int = 20):
    """List recent workflows (running + completed) using sorted set index."""
    service = OrchestrationService()
    return await service.list_workflows(limit=limit)


@router.get("/workflows/{workflow_id}")
async def workflow_status(workflow_id: str):
    """Retrieve workflow status and live step progress updates."""
    service = OrchestrationService()
    data = await service.get_workflow_status(workflow_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@router.post("/admin_review")
async def admin_review(req: AdminReviewRequest):
    """Spawn an admin / QA review task for an existing job result."""
    service = OrchestrationService()
    return await service.admin_review(req.job_id, req.review_prompt)
