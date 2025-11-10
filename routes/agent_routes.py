
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from services.agent_service import AgentService
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="workspace/templates")

@router.get("/dashboard/agents", response_class=HTMLResponse)
async def agents_dashboard(request: Request):
    agents = await AgentService.list_agents()
    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "agents": agents, "active_tab": "agents"},
    )

@router.post("/dashboard/agents/register", response_class=HTMLResponse)
async def register_agent(request: Request, name: str = Form(...), role: str = Form(...), model: str = Form(...)):
    await AgentService.register_agent(name, role, model)
    agents = await AgentService.list_agents()
    return templates.TemplateResponse(
        "partials_agents_table.html", {"request": request, "agents": agents}
    )
