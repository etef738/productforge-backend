import json, time
from core.redis_client import get_redis_client
from crewai import Agent, Task, Crew
from openai import OpenAI

AGENT_KEY = "agents_registry"
client = OpenAI()

class AgentService:
    @staticmethod
    async def register_agent(name: str, role: str, model: str = "gpt-4o-mini"):
        r = get_redis_client()
        agent_data = {
            "name": name,
            "role": role,
            "model": model,
            "status": "ready",
        }
        await r.hset("agent:" + name, mapping=agent_data)
        return AgentService.create_agent_instance(agent_data)

    @staticmethod
    def create_agent_instance(agent_data):
        return Agent(
            role=agent_data["role"],
            goal=f"Perform {agent_data['role']} responsibilities efficiently.",
            backstory=f"{agent_data['name']} is a specialized AI agent designed for {agent_data['role']}.",
            llm=agent_data["model"]
        )

    @staticmethod
    async def list_agents():
        r = get_redis_client()
        keys = await r.keys("agent:*")
        agents = []
        for k in keys:
            agents.append(await r.hgetall(k))
        return agents

    @staticmethod
    async def run_agent_task(agent_name: str, prompt: str):
        r = get_redis_client()
        agent_data = await r.hgetall(f"agent:{agent_name}")
        if not agent_data:
            return {"error": "Agent not found"}
        agent = AgentService.create_agent_instance(agent_data)
        task = Task(
            description=prompt,
            expected_output="A concise completion for the given request.",
            agent=agent
        )
        crew = Crew(agents=[agent], tasks=[task])
        result = crew.kickoff()
        await r.set(f"agent_result:{agent_name}", result)
        await r.hset(f"agent:{agent_name}", "status", "completed")
        return {"agent": agent_name, "result": result}
