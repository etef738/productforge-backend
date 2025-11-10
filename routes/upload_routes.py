"""
File upload routes with indexed listing support.
"""


from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from services.upload_service import UploadService

router = APIRouter(prefix="/upload", tags=["Upload"])

# Phase 11: Modern upload endpoint
@router.post("/file")
async def upload_file(file: UploadFile = File(...)):
    try:
        result = await UploadService.upload_file(file)
        return JSONResponse(result)
    except Exception as e:
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

