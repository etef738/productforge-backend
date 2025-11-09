"""
Common utility functions used across the application.
"""
import os
from datetime import datetime
from typing import Optional


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def get_human_timestamp() -> str:
    """Get human-readable timestamp."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file system usage."""
    # Replace spaces and unsafe characters with underscores
    safe_name = ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)
    return safe_name


def get_upload_dir() -> str:
    """Get upload directory based on environment (Railway vs local)."""
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return "/tmp/uploads"
    return "workspace/uploads"


def get_log_dir() -> str:
    """Get log directory based on environment (Railway vs local)."""
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return "/tmp/logs"
    return "workspace/logs"


def ensure_directory(directory: str) -> None:
    """Ensure directory exists, create if it doesn't."""
    os.makedirs(directory, exist_ok=True)


def calculate_uptime(start_time: float) -> dict:
    """Calculate uptime from start timestamp."""
    uptime_seconds = round(datetime.now().timestamp() - start_time, 2)
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    
    return {
        "seconds": uptime_seconds,
        "human": f"{hours}h {minutes}m {seconds}s"
    }
