"""Structured logging middleware with daily log rotation.

Logs a single concise line per request in production format:
  <ts> method=GET path=/system/health status=200 duration_ms=12.34 ip=127.0.0.1

Files are rotated daily into either:
  - workspace/logs/app.log (local)
  - /tmp/logs/app.log (Railway)
"""
from __future__ import annotations

import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def _ensure_logger() -> logging.Logger:
    logger = logging.getLogger("pf.access")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Decide log directory per environment
    base_dir = "/tmp/logs" if os.environ.get("RAILWAY_ENVIRONMENT") else "workspace/logs"
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(base_dir, "app.log")

    handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=7, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s method=%(method)s path=%(path)s status=%(status)d duration_ms=%(duration).2f ip=%(ip)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also log to stdout for local dev visibility
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    return logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that logs method, path, status, and duration."""

    def __init__(self, app):
        super().__init__(app)
        self.logger = _ensure_logger()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            # Ensure errors are logged with 500 status
            status = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            ip = request.client.host if request.client else "-"
            # Supply extra attributes for the formatter
            self.logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration": duration_ms,
                    "ip": ip,
                },
            )
        return response
