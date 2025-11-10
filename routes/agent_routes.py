
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from services.agent_service import AgentService

router = APIRouter(prefix="/dashboard/agents", tags=["Agents"])
templates = Jinja2Templates(directory="workspace/templates")

@router.get("", response_class=HTMLResponse)
async def agents_dashboard(request: Request):
    agents = await AgentService.list_agents()
    return templates.TemplateResponse("agents.html", {"request": request, "agents": agents})

@router.post("/register")
async def register_agent_ui(request: Request, name: str = Form(...), role: str = Form(...), model: str = Form("gpt-4o-mini")):
    await AgentService.register_agent(name, role, model)
    agents = await AgentService.list_agents()
    return templates.TemplateResponse("partials_agents_table.html", {"request": request, "agents": agents})

@router.post("/run")
async def run_task(request: Request, agent_name: str = Form(...), prompt: str = Form(...)):
    result = await AgentService.run_agent_task(agent_name, prompt)
    return JSONResponse(result)
