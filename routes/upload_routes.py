
from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from core.redis_client import get_redis_client
from services.upload_service import handle_upload
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="workspace/templates")
router = APIRouter(prefix="/dashboard/upload", tags=["Upload"])


@router.get("", response_class=HTMLResponse)
async def upload_dashboard(request: Request):
    """Render the Upload dashboard page."""
    return templates.TemplateResponse("upload.html", {"request": request})


@router.post("/file", response_class=HTMLResponse)
async def upload_file(request: Request, file: UploadFile = File(...)):
    """
    Handle file uploads via HTMX.
    - Saves file temporarily.
    - Stores upload result in Redis for observability.
    - Returns an HTML partial (partials_upload_result.html) rendered live.
    """
    redis = get_redis_client()
    result = await handle_upload(file, redis)
    context = {"request": request, "result": result}
    return templates.TemplateResponse("partials_upload_result.html", context)

