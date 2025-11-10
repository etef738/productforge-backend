
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from services.agent_service import AgentService
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="workspace/templates")

@router.get("/dashboard/agents", response_class=HTMLResponse)
async def dashboard_agents(request: Request):
    agents = AgentService.list_agents()
    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "active_tab": "agents", "agents": agents},
    )

@router.post("/dashboard/agents/register", response_class=HTMLResponse)
async def register_agent(request: Request, name: str = Form(...), role: str = Form(...), model: str = Form(...)):
    AgentService.register_agent(name, role, model)
    agents = AgentService.list_agents()
    return templates.TemplateResponse("partials_agents_table.html", {"request": request, "agents": agents})
