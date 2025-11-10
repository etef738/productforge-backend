from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from services.agent_service import register_agent, list_agents, run_agent_task

router = APIRouter()
templates = Jinja2Templates(directory="workspace/templates")

@router.get("/dashboard/agents", response_class=HTMLResponse)
async def dashboard_agents(request: Request):
    agents = await list_agents()
    # Do NOT 'await' agents here; just pass the list to the template
    return templates.TemplateResponse("agents.html", {"request": request, "agents": agents, "active_tab": "agents"})

@router.post("/dashboard/agents/register")
async def register_agent_ui(request: Request, name: str = Form(...), role: str = Form(...), model: str = Form("gpt-4o-mini")):
    await register_agent(name, role, model)
    agents = await list_agents()
    return templates.TemplateResponse("partials_agents_table.html", {"request": request, "agents": agents})

@router.post("/dashboard/agents/run")
async def run_task(request: Request, agent_name: str = Form(...), prompt: str = Form(...)):
    result = await run_agent_task(agent_name, prompt)
    return JSONResponse(result)
