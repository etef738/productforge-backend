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
    return templates.TemplateResponse("help.html", {"request": request, "active_tab": "overview"})

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Serve the generated reports listing page."""
    return templates.TemplateResponse("reports.html", {"request": request, "active_tab": "reports"})

# ===========================
# New Phase 7 dashboard pages
# ===========================
from services.upload_service import UploadService
from services.agent_service import AgentService
from services.result_service import ResultService
from services.orchestration_service import OrchestrationService
from core.metrics import get_metrics
from fastapi.responses import JSONResponse
import time


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
    agents = await AgentService.list_agents()
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


@router.get("/observability", response_class=HTMLResponse)
async def observability_page(request: Request):
    """Observability page with live metrics and charts."""
    return templates.TemplateResponse("observability.html", {"request": request, "active_tab": "observability"})


# ===========================
# Phase 8: Live Dashboard APIs
# ===========================

@router.get("/api/stats")
async def dashboard_stats():
    """Return live dashboard statistics for HTMX polling.
    
    Returns JSON with uptime, total requests, Redis latency, cache hit rate.
    Auto-refreshed by HTMX every 5 seconds.
    """
    metrics = get_metrics()
    metrics.increment_dashboard_refresh()
    
    return JSONResponse(content=metrics.to_dict())


@router.get("/api/stats-html", response_class=HTMLResponse)
async def dashboard_stats_html(request: Request):
    """Return live dashboard statistics as HTML for HTMX polling.
    
    Returns HTML metric cards for system pulse panel.
    Auto-refreshed by HTMX every 5 seconds.
    """
    metrics = get_metrics()
    metrics.increment_dashboard_refresh()
    
    stats = metrics.to_dict()
    uptime_hours = round(stats["uptime_seconds"] / 3600, 1)
    
    return templates.TemplateResponse("partials_stats.html", {
        "request": request,
        "uptime_hours": uptime_hours,
        "total_requests": stats["total_requests"],
        "redis_latency_ms": stats["redis_latency_ms"],
        "cache_hit_rate": stats["cache_hit_rate"]
    })


@router.get("/api/recent-uploads")
async def recent_uploads_api():
    """Return recent uploads as JSON for HTMX partial refresh."""
    metrics = get_metrics()
    metrics.increment_htmx_event()
    
    service = UploadService()
    uploads = service.list_uploads(limit=10)
    
    return JSONResponse(content={"uploads": uploads, "count": len(uploads)})


@router.get("/api/recent-uploads-html", response_class=HTMLResponse)
async def recent_uploads_html(request: Request):
    """Return recent uploads as HTML table for HTMX polling."""
    metrics = get_metrics()
    metrics.increment_htmx_event()
    
    service = UploadService()
    uploads = service.list_uploads(limit=10)
    
    return templates.TemplateResponse("partials_uploads_table.html", {
        "request": request,
        "uploads": uploads
    })


@router.get("/api/recent-workflows")
async def recent_workflows_api():
    """Return recent workflows as JSON for HTMX partial refresh."""
    metrics = get_metrics()
    metrics.increment_htmx_event()
    
    service = OrchestrationService()
    workflows = await service.list_workflows(limit=10)
    
    return JSONResponse(content={"workflows": workflows, "count": len(workflows)})


@router.get("/api/upload-metrics-html", response_class=HTMLResponse)
async def upload_metrics_html(request: Request):
    """Return upload metrics panel for the upload page (HTMX)."""
    m = get_metrics().to_dict()
    return templates.TemplateResponse(
        "partials_upload_metrics.html",
        {
            "request": request,
            "upload_requests_total": m.get("upload_requests_total", 0),
            "upload_failures_total": m.get("upload_failures_total", 0),
            "upload_avg_duration_ms": m.get("upload_avg_duration_ms", 0.0),
        },
    )

