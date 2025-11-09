"""
Task service for managing task queue and dispatch.
"""
import json
from typing import Dict, Any
from uuid import uuid4
from datetime import datetime
from core.redis_client import get_redis_client
from models.results_models import TaskRequest
from services.agent_service import AgentService


class TaskService:
    """Service for task queue management."""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.agent_service = AgentService()
    
    def queue_task(self, task: TaskRequest) -> Dict[str, Any]:
        """Queue a task for processing."""
        job_id = str(uuid4())
        
        # Auto-assign agent if not specified
        if not task.agent_name:
            task.agent_name = self._auto_assign_agent(task.job)
        
        # Create payload
        payload = {
            "job_id": job_id,
            "job": task.job,
            "task": task.job,  # Include task description
            "agent_name": task.agent_name,
            "priority": task.priority,
            "requires_qa": task.requires_qa,
            "created_at": datetime.now().isoformat(),
            "mode": "agent_dispatch"
        }
        
        # Update agent task count
        self.agent_service.increment_task_count(task.agent_name)
        
        # Queue with priority
        queue_name = f"queue_{task.priority}" if task.priority != "normal" else "queue"
        self.redis.lpush(queue_name, json.dumps(payload))
        
        return {
            "status": "queued",
            "job_id": job_id,
            "agent": task.agent_name,
            "queue": queue_name
        }
    
    def _auto_assign_agent(self, job_description: str) -> str:
        """Auto-assign agent based on job description."""
        agents = self.agent_service.list_agents()
        
        if not agents:
            # Create default agents if none exist
            self.agent_service.create_default_agents()
            return "general_assistant"
        
        # Simple keyword-based assignment
        job_lower = job_description.lower()
        
        # Role-based assignment logic
        if any(word in job_lower for word in ["test", "qa", "quality", "validate", "verify"]):
            qa_agent = next((a for a in agents if a.role == "QA"), None)
            return qa_agent.name if qa_agent else "general_assistant"
        
        elif any(word in job_lower for word in ["debug", "fix", "error", "bug"]):
            debug_agent = next((a for a in agents if a.role == "Debug"), None)
            return debug_agent.name if debug_agent else "general_assistant"
        
        elif any(word in job_lower for word in ["analyze", "review", "audit", "inspect"]):
            analyzer_agent = next((a for a in agents if a.role == "Analyze"), None)
            return analyzer_agent.name if analyzer_agent else "general_assistant"
        
        return "general_assistant"
    
    def get_queue_length(self, queue_name: str = "queue") -> int:
        """Get the current queue length."""
        return self.redis.llen(queue_name)
    
    def get_total_queued_jobs(self) -> int:
        """Get total number of queued jobs across all queues."""
        total = 0
        for queue in ["queue", "queue_high", "queue_low"]:
            total += self.redis.llen(queue)
        return total
