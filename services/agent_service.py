"""
Agent service for managing agents in the system.
Optimized with Redis indices and simple caching.
"""
import json
import time
from typing import List, Optional
from datetime import datetime
from functools import lru_cache
from core.redis_client import get_redis_client, AGENTS_INDEX, index_agent, list_agents_index
from core.exceptions import AgentNotFoundException
from models.agent_models import Agent


class AgentService:
    """Service for agent management operations."""
    
    def __init__(self):
        self.redis = get_redis_client()
    
    def create_agent(self, agent: Agent) -> Agent:
        """Create a new agent."""
        agent.created_at = datetime.now().isoformat()
        agent.task_count = 0
        
        key = f"agent:{agent.name}"
        self.redis.set(key, agent.model_dump_json())
        # Update index
        index_agent(agent.name, agent.created_at)
        self._invalidate_cache()
        return agent
    
    def get_agent(self, agent_name: str) -> Optional[Agent]:
        """Get agent by name."""
        key = f"agent:{agent_name}"
        data = self.redis.get(key)
        if data:
            return Agent.model_validate_json(data)
        return None
    
    def list_agents(self) -> List[Agent]:
        """List all agents."""
        # Use index to list agent names; then fetch
        names = list_agents_index(limit=200)
        agents: List[Agent] = []
        pipeline = self.redis.pipeline()
        for name in names:
            pipeline.get(f"agent:{name}")
        raw = pipeline.execute()
        for item in raw:
            if item:
                agents.append(Agent.model_validate_json(item))
        return agents
    
    def delete_agent(self, agent_name: str) -> bool:
        """Delete an agent."""
        key = f"agent:{agent_name}"
        return bool(self.redis.delete(key))
    
    def increment_task_count(self, agent_name: str) -> None:
        """Increment task count for an agent."""
        agent = self.get_agent(agent_name)
        if agent:
            agent.task_count += 1
            agent.last_assigned = datetime.now().isoformat()
            key = f"agent:{agent_name}"
            self.redis.set(key, agent.model_dump_json())
            self._invalidate_cache()
    
    def create_default_agents(self) -> List[Agent]:
        """Create default system agents."""
        default_agents = [
            Agent(
                name="general_assistant",
                role="Assistant",
                description="General-purpose AI assistant for various tasks",
                skills=["general_help", "analysis", "writing"],
                model="gpt-4o-mini"
            ),
            Agent(
                name="analyzer_bot",
                role="Analyze",
                description="Reads uploaded projects and generates structured analysis reports",
                skills=["code_summary", "file_classification", "architecture_analysis"],
                model="gpt-4o-mini"
            ),
            Agent(
                name="qa_bot",
                role="QA",
                description="Reviews AI outputs and scores their correctness",
                skills=["evaluation", "fact_check", "quality_review"],
                model="gpt-4o-mini"
            ),
            Agent(
                name="debugger_bot",
                role="Debug",
                description="Runs code lint and identifies errors or logic gaps",
                skills=["static_analysis", "error_fix", "performance_optimization"],
                model="gpt-4o-mini"
            )
        ]
        
        created = []
        for agent in default_agents:
            key = f"agent:{agent.name}"
            if not self.redis.exists(key):
                created.append(self.create_agent(agent))
        
        return created

    # ----------------------------
    # Caching helpers
    # ----------------------------
    @lru_cache(maxsize=1)
    def cached_agent_names(self) -> tuple:
        """Cache of agent names list; invalidated on writes.
        Returns a tuple for hashability in lru_cache.
        """
        return tuple(list_agents_index(limit=500))

    def _invalidate_cache(self):
        try:
            self.cached_agent_names.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
