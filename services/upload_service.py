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
    
    @staticmethod
    async def upload_file(file):
        import time
        from core.metrics import upload_requests_total, upload_failures_total, upload_duration_seconds
        start = time.perf_counter()
        filename = file.filename

        if upload_requests_total:
            upload_requests_total.inc()

        try:
            # Save file
            content = await file.read()
            saved_path = f"workspace/uploads/{filename}"
            with open(saved_path, "wb") as f:
                f.write(content)
            duration_ms = (time.perf_counter() - start) * 1000
            if upload_duration_seconds:
                upload_duration_seconds.observe(duration_ms / 1000)

            return {
                "status": "success",
                "filename": filename,
                "duration_ms": round(duration_ms, 2),
                "metrics": {
                    "uploads": upload_requests_total._value.get() if upload_requests_total else 0,
                    "failures": upload_failures_total._value.get() if upload_failures_total else 0,
                },
            }
        except Exception as e:
            if upload_failures_total:
                upload_failures_total.inc()
            raise e
    
    def list_uploads(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent uploads using sorted set index (no scans)."""
        return list_uploads_from_index(limit=limit)

