"""
Dashboard and UI routes.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

templates = Jinja2Templates(directory="workspace/templates")


@router.get("/ping")
async def ping():
    """Ping endpoint to check if dashboard module is alive."""
    return {"status": "ok", "module": "dashboard"}


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_tab": "overview"})


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    """Serve the help and FAQ page."""
    return templates.TemplateResponse("help.html", {"request": request})

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Serve the generated reports listing page."""
    return templates.TemplateResponse("reports.html", {"request": request})

# ===========================
# New Phase 7 dashboard pages
# ===========================
from services.upload_service import UploadService
from services.agent_service import AgentService
from services.result_service import ResultService
from services.orchestration_service import OrchestrationService


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Upload page with form and recent uploads list."""
    # Server-side: fetch recent uploads via service to pass to template
    uploads = []
    try:
        service = UploadService()
        uploads = service.list_uploads(limit=20)
    except Exception:
        uploads = []
    return templates.TemplateResponse("upload.html", {"request": request, "uploads": uploads, "active_tab": "upload"})


@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    """Agents page listing registered agents."""
    service = AgentService()
    agents = service.list_agents()
    return templates.TemplateResponse("agents.html", {"request": request, "agents": agents, "active_tab": "agents"})


@router.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    """Results page listing recent results."""
    service = ResultService()
    results = service.list_results(limit=20)
    return templates.TemplateResponse("results.html", {"request": request, "results": results, "active_tab": "results"})


@router.get("/workflows", response_class=HTMLResponse)
async def workflows_page(request: Request):
    """Workflows page with orchestrate form and recent workflows."""
    service = OrchestrationService()
    workflows_data = await service.list_workflows(limit=20)
    return templates.TemplateResponse("workflows.html", {"request": request, "workflows": workflows_data, "active_tab": "workflows"})
