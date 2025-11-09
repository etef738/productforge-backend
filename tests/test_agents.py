"""
Tests for agent service and routes.
"""
import pytest
from services.agent_service import AgentService
from models.agent_models import Agent


def test_create_agent():
    """Test agent creation."""
    service = AgentService()
    
    agent = Agent(
        name="test_agent",
        role="Test",
        description="Test agent",
        skills=["testing"]
    )
    
    created = service.create_agent(agent)
    assert created.name == "test_agent"
    assert created.role == "Test"
    assert created.task_count == 0


def test_list_agents():
    """Test listing agents."""
    service = AgentService()
    agents = service.list_agents()
    assert isinstance(agents, list)


def test_get_agent():
    """Test getting a specific agent."""
    service = AgentService()
    
    # Create agent first
    agent = Agent(name="test_get", role="Test")
    service.create_agent(agent)
    
    # Get agent
    retrieved = service.get_agent("test_get")
    assert retrieved is not None
    assert retrieved.name == "test_get"


def test_delete_agent():
    """Test deleting an agent."""
    service = AgentService()
    
    # Create agent first
    agent = Agent(name="test_delete", role="Test")
    service.create_agent(agent)
    
    # Delete agent
    deleted = service.delete_agent("test_delete")
    assert deleted is True
    
    # Verify deletion
    retrieved = service.get_agent("test_delete")
    assert retrieved is None
