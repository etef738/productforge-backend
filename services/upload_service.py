# Upload service for handling file uploads with Redis indexing.
# 
# Ensure workspace/uploads exists on startup (fixes 502 on Railway)
"""
Upload service for handling file uploads with Redis indexing.
"""
import os
from typing import Dict, Any, List
from uuid import uuid4
import tempfile
import zipfile
import json
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

from prometheus_client import Counter, Histogram

# Prometheus metrics
upload_counter = Counter("uploads_total", "Total number of file uploads")
upload_failures = Counter("upload_failures_total", "Total failed uploads")
upload_latency = Histogram("upload_duration_seconds", "Time taken for uploads")

async def handle_upload(file: UploadFile, redis):
    """
    Handles a file upload.
    - Saves uploaded ZIP temporarily
    - Extracts metadata
    - Updates Prometheus metrics + Redis observability
    """
    start_time = time.time()
    try:
        # Save file to a temp location
        suffix = ".zip" if file.filename.endswith(".zip") else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Basic validation: must be a zip
        if not zipfile.is_zipfile(tmp_path):
            upload_failures.inc()
            return json.dumps({"status": "error", "message": "Invalid file type. Must be a ZIP."})

        # Count + metrics
        upload_counter.inc()
        duration = round(time.time() - start_time, 2)
        upload_latency.observe(duration)

        # Store upload info in Redis
        upload_info = {
            "status": "success",
            "filename": file.filename,
            "duration_ms": duration * 1000,
            "metrics": {"uploads": float(upload_counter._value.get()), "failures": float(upload_failures._value.get())}
        }
        await redis.set(f"upload:{file.filename}", json.dumps(upload_info))
        await redis.lpush("recent_uploads", json.dumps(upload_info))

        return json.dumps(upload_info)

    except Exception as e:
        upload_failures.inc()
        return json.dumps({"status": "error", "message": str(e)})

    finally:
        # Cleanup temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass
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

