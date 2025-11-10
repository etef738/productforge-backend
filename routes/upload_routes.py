"""
File upload routes with indexed listing support.
"""


from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import time
from fastapi.responses import JSONResponse
from services.upload_service import save_uploaded_file, UploadService
from core.metrics import get_metrics
from core.exceptions import UploadException
import logging

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger("upload")

# Modern upload endpoint
@router.post("/file")
async def upload_file_modern(file: UploadFile = File(...)):
    metrics = get_metrics()
    start = time.time()
    metrics.increment_upload_request()
    try:
        path = await save_uploaded_file(file)
        duration_ms = (time.time() - start) * 1000.0
        metrics.record_upload_duration_ms(duration_ms)
        logger.info(f"✅ Uploaded file saved to {path}")
        return JSONResponse({
            "status": "success",
            "filename": file.filename,
            "path": path,
            "metrics": {
                "upload_count": metrics.to_dict()["upload_requests_total"],
                "failure_count": metrics.to_dict()["upload_failures_total"],
                "average_duration_ms": metrics.to_dict()["upload_avg_duration_ms"],
                "last_duration_ms": round(duration_ms, 2)
            }
        })
    except Exception as e:
        metrics.increment_upload_failure()
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

