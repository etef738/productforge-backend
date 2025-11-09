"""
Result and task-related Pydantic models.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TaskRequest(BaseModel):
    """Task request model for creating new tasks."""
    job: str = Field(..., description="Task description")
    agent_name: Optional[str] = Field(None, description="Specific agent to handle the task")
    priority: Optional[str] = Field("normal", description="Task priority: low, normal, high")
    requires_qa: Optional[bool] = Field(False, description="Whether task needs QA review")


class EnhancedResult(BaseModel):
    """Enhanced result model with full traceability."""
    job_id: str
    workflow_id: Optional[str] = Field(None, description="Associated workflow ID")
    parent_job_id: Optional[str] = Field(None, description="Parent job if this is a review/follow-up")
    agent: Optional[str] = Field(None, description="Agent name")
    role: Optional[str] = Field(None, description="Agent role")
    reviewed_by: Optional[str] = Field(None, description="Agent that reviewed this result")
    status: str = Field(default="completed", description="Task status: queued, processing, completed, failed")
    output: Optional[str] = Field(None, description="Task output")
    started_at: Optional[str] = Field(None, description="Task start time")
    completed_at: Optional[str] = Field(None, description="Task completion time")
    execution_time: Optional[float] = Field(None, description="Task execution time in seconds")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Result timestamp")
    task: Optional[str] = Field(None, description="Original task description")
