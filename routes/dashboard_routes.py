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
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    """Serve the help and FAQ page."""
    return templates.TemplateResponse("help.html", {"request": request})
