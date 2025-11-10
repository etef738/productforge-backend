"""
Upload service for handling file uploads with Redis indexing.
"""
import os
from typing import Dict, Any, List
from uuid import uuid4
from fastapi import UploadFile
from core.utils import get_upload_dir, ensure_directory, sanitize_filename
from core.exceptions import UploadException
from core.redis_client import get_redis_client, index_upload, list_uploads as list_uploads_from_index

import os
import json
import time
from typing import Dict, Any, List
from uuid import uuid4
from datetime import datetime
from fastapi import UploadFile
from core.utils import get_upload_dir, ensure_directory, sanitize_filename
from core.exceptions import UploadException
from core.redis_client import get_redis_client, index_upload, list_uploads as list_uploads_from_index
from core.metrics import get_metrics

# Ensure workspace/uploads exists on startup (fixes 502 on Railway)
UPLOAD_DIR = "workspace/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def save_uploaded_file(file: UploadFile) -> str:
    """Save an uploaded file to the workspace/uploads directory.
    
    Args:
        file: The uploaded file from FastAPI
        
    Returns:
        str: Path to the saved file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(UPLOAD_DIR, f"{timestamp}_{file.filename}")
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return dest


class UploadService:
    """Service for file upload management with indexed storage."""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.upload_dir = get_upload_dir()
        ensure_directory(self.upload_dir)
    
    async def upload_file(
        self,
        file: UploadFile,
        project_name: str = "",
        max_size: int = 50 * 1024 * 1024  # 50MB default
    ) -> Dict[str, Any]:
        """Upload a file and queue it for analysis.
        
        Uses Redis sorted set index for efficient listing without scans.
        """
        
        # Validate file type
        if not file.filename.endswith(".zip"):
            raise UploadException("Only ZIP files are allowed")

        start_time = time.time()
        metrics = get_metrics()
        metrics.increment_upload_request()

        # Read content
        content = await file.read()
        
        # Validate size
        if len(content) > max_size:
            raise UploadException(f"File too large (max {max_size // (1024*1024)}MB)")
        
        # Sanitize filename and generate upload ID
        safe_filename = sanitize_filename(file.filename)
        upload_id = str(uuid4())
        file_path = os.path.join(self.upload_dir, f"{upload_id}_{safe_filename}")
        
        # Save file
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            metrics.increment_upload_failure()
            raise UploadException(f"Failed to save file: {e}")
        
        # Create job for processing
        job_id = str(uuid4())
        payload = {
            "job_id": job_id,
            "job": f"Analyze uploaded archive: {file.filename}",
            "task": f"Analyze uploaded archive: {file.filename}",
            "file_path": file_path,
            "mode": "analyze",
            "project": project_name or "unknown",
            "created_at": datetime.now().isoformat()
        }
        
        # Queue for processing
        self.redis.lpush("queue", json.dumps(payload))
        
        # Index upload for fast retrieval
        upload_metadata = {
            "upload_id": upload_id,
            "filename": safe_filename,
            "original_filename": file.filename,
            "size": len(content),
            "file_path": file_path,
            "job_id": job_id,
            "project": project_name or "unknown",
            "uploaded_at": datetime.now().isoformat()
        }
        index_upload(upload_id, upload_metadata)
        
        duration_ms = (time.time() - start_time) * 1000.0
        metrics.record_upload_duration_ms(duration_ms)

        return {
            "status": "uploaded",
            "upload_id": upload_id,
            "path": file_path,
            "job_id": job_id,
            "filename": safe_filename,
            "size": len(content),
            "metrics": {
                "upload_count": metrics.to_dict()["upload_requests_total"],
                "failure_count": metrics.to_dict()["upload_failures_total"],
                "average_duration_ms": metrics.to_dict()["upload_avg_duration_ms"],
                "last_duration_ms": round(duration_ms, 2)
            }
        }
    
    def list_uploads(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent uploads using sorted set index (no scans)."""
        return list_uploads_from_index(limit=limit)

