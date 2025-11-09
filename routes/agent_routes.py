"""
Agent management routes.
"""
from fastapi import APIRouter, HTTPException
from typing import List
from models.agent_models import Agent
from services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/ping")
async def ping():
    """Ping endpoint to check if agents module is alive."""
    return {"status": "ok", "module": "agents"}


@router.post("/", response_model=Agent)
async def register_agent(agent: Agent):
    """Register a new agent in the system."""
    service = AgentService()
    return service.create_agent(agent)


@router.get("/", response_model=List[Agent])
async def list_agents():
    """List all registered agents."""
    service = AgentService()
    agents = service.list_agents()
    
    # Create default agents if none exist
    if not agents:
        service.create_default_agents()
        agents = service.list_agents()
    
    return agents


@router.get("/{agent_name}", response_model=Agent)
async def get_agent(agent_name: str):
    """Get a specific agent by name."""
    service = AgentService()
    agent = service.get_agent(agent_name)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    return agent


@router.delete("/{agent_name}")
async def delete_agent(agent_name: str):
    """Delete an agent."""
    service = AgentService()
    deleted = service.delete_agent(agent_name)
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    return {"status": "deleted", "agent": agent_name}
