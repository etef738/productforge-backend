"""
Agent-related Pydantic models.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class Agent(BaseModel):
    """Agent model for registration and management."""
    name: str = Field(..., description="Unique agent name")
    role: str = Field(..., description="Agent's core function (e.g. 'QA', 'Debugger', 'Analyzer')")
    description: Optional[str] = Field(None, description="Detailed role or purpose")
    skills: List[str] = Field(default_factory=list, description="Capabilities or prompts")
    model: Optional[str] = Field("gpt-4o-mini", description="Default AI model for this agent")
    task_count: int = Field(default=0, description="Number of tasks completed")
    created_at: Optional[str] = Field(None, description="Agent creation timestamp")
    last_assigned: Optional[str] = Field(None, description="Last task assignment timestamp")


class AgentResponse(BaseModel):
    """Response from an agent after task execution."""
    agent_name: str
    role: str
    output: str
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    review_needed: Optional[bool] = Field(False)
