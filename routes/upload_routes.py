"""
File upload routes with indexed listing support.
"""


from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from services.upload_service import save_uploaded_file, UploadService
from core.metrics import UPLOAD_COUNTER
from core.exceptions import UploadException
import logging

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger("upload")

# Modern upload endpoint
@router.post("/file")
async def upload_file_modern(file: UploadFile = File(...)):
    try:
        path = await save_uploaded_file(file)
        UPLOAD_COUNTER.inc()
        logger.info(f"✅ Uploaded file saved to {path}")
        return JSONResponse({"status": "success", "filename": file.filename, "path": path})
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Legacy endpoints for backward compatibility
@router.get("/ping")
async def ping():
    """Ping endpoint to check if upload module is alive."""
    return {"status": "ok", "module": "upload"}

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    project: str = Form(default="")
):
    """Upload a ZIP file for analysis."""
    service = UploadService()
    try:
        result = await service.upload_file(file, project_name=project)
        return result
    except UploadException as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/list")
async def list_uploads(limit: int = 20):
    """List recent uploads using sorted set index (O(log n + k))."""
    service = UploadService()
    uploads = service.list_uploads(limit=limit)
    return {
        "uploads": uploads,
        "count": len(uploads)
    }

