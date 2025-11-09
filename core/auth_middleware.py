"""API Key authentication middleware.

Requires X-API-Key header matching the environment variable API_KEY for
protected routes. The following paths are excluded:
  - /dashboard
  - /help
  - /system/health

If API_KEY is not set, the middleware is effectively disabled (no auth).
"""
from __future__ import annotations

import os
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


EXCLUDED_PATHS: Iterable[str] = (
    "/dashboard",
    "/help",
    "/system/health",
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.api_key = os.environ.get("API_KEY")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Disabled when no API key configured
        if not self.api_key:
            return await call_next(request)

        # Allow excluded paths without auth
        path = request.url.path
        if any(path.startswith(p) for p in EXCLUDED_PATHS):
            return await call_next(request)

        # Validate header
        header_key = request.headers.get("X-API-Key")
        if header_key != self.api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        return await call_next(request)
