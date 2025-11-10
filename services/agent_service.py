
import json, time
from core.redis_client import get_redis_client

AGENT_KEY = "agents_registry"

class AgentService:
    @staticmethod
    async def register_agent(name: str, role: str, model: str):
        r = get_redis_client()
        agent_id = f"{name.lower()}_{int(time.time())}"
        agent = {
            "id": agent_id,
            "name": name,
            "role": role,
            "model": model,
            "status": "active",
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_heartbeat": time.time(),
        }
        await r.hset(AGENT_KEY, agent_id, json.dumps(agent))
        return agent

    @staticmethod
    async def list_agents():
        r = get_redis_client()
        raw_agents = await r.hgetall(AGENT_KEY)
        return [json.loads(v) for v in raw_agents.values()] if raw_agents else []

    @staticmethod
    async def update_heartbeat(agent_id: str):
        r = get_redis_client()
        raw = await r.hget(AGENT_KEY, agent_id)
        if raw:
            agent = json.loads(raw)
            agent["last_heartbeat"] = time.time()
            await r.hset(AGENT_KEY, agent_id, json.dumps(agent))
            return agent
        return None
