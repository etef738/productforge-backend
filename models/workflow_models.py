"""
Workflow-related Pydantic models.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class WorkflowStep(BaseModel):
    """Individual step in a workflow."""
    step: int
    role: str
    agent: str
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    execution_time: Optional[float] = None
    output_preview: Optional[str] = None


class WorkflowStatus(BaseModel):
    """Complete workflow status."""
    workflow_id: str
    total_steps: int
    completed_steps: int = 0
    status: str = "in_progress"
    total_execution_time: float = 0.0
    steps: List[WorkflowStep] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
