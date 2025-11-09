"""
Routes package initialization.
Export all routers for easy registration.
"""
from routes.system_routes import router as system_router
from routes.agent_routes import router as agent_router
from routes.orchestration_routes import router as orchestration_router
from routes.result_routes import router as result_router
from routes.dashboard_routes import router as dashboard_router
from routes.upload_routes import router as upload_router

__all__ = [
    "system_router",
    "agent_router",
    "orchestration_router",
    "result_router",
    "dashboard_router",
    "upload_router"
]
