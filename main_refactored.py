"""
ProductForge Backend - Enterprise Grade FastAPI Application
Modular architecture with clean separation of concerns.
"""
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import uvicorn

# Import core modules
from core.exceptions import global_exception_handler
from core.redis_client import get_redis_client
from core.openai_client import validate_openai_key
from core.middleware import LoggingMiddleware
from core.auth_middleware import APIKeyMiddleware

# Import routers
from routes.system_routes import router as system_router
from routes.agent_routes import router as agent_router
from routes.orchestration_routes import router as orchestration_router
from routes.result_routes import router as result_router
from routes.dashboard_routes import router as dashboard_router
from routes.upload_routes import router as upload_router
from routes.metrics_routes import router as metrics_router
from routes.analytics_routes import router as analytics_router
from routes.reports_routes import router as reports_router

# Configuration
from config import settings, validate_environment
from core.logging_config import get_logger
from services.deploy_check_service import DeployCheckService

# Initialize logger
logger = get_logger(__name__)

# ===========================
# ENVIRONMENT SETUP
# ===========================
load_dotenv()
validate_environment()

# Track backend startup time for health monitoring
BACKEND_START_TIME = time.time()

# ===========================
# LIFESPAN CONTEXT MANAGER
# ===========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown events."""
    # STARTUP
    logger.info("🚀 ProductForge Backend Starting...")
    logger.info(f"Environment: {'Railway' if os.environ.get('RAILWAY_ENVIRONMENT') else 'Local'}")
    logger.info(f"Version: 2.0.0")
    
    # Metrics initialization log
    from core.metrics import get_metrics
    _ = get_metrics()
    logger.info("✅ Metrics ready")
    
    # Run deployment verification
    deploy_service = DeployCheckService()
    verification = await deploy_service.verify_startup()
    
    if verification["status"] == "healthy":
        logger.info("✅✅✅ Railway boot OK - All systems operational ✅✅✅")
    elif verification["status"] == "degraded":
        logger.warning(f"⚠️ Railway boot DEGRADED - {len(verification['warnings'])} warnings")
        for warning in verification["warnings"]:
            logger.warning(f"  ⚠️ {warning}")
    else:
        logger.error(f"❌ Railway boot FAILED - {len(verification['warnings'])} errors")
        for warning in verification["warnings"]:
            logger.error(f"  ❌ {warning}")
    
    yield  # Application runs here
    
    # SHUTDOWN
    logger.info("👋 ProductForge Backend Shutting Down...")

# ===========================
# APPLICATION INITIALIZATION
# ===========================
app = FastAPI(
    title="ProductForge Backend",
    description="Enterprise-grade multi-agent AI orchestration platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ===========================
# JINJA2 TEMPLATES
# ===========================
templates = Jinja2Templates(directory="workspace/templates")

# ===========================
# MIDDLEWARE CONFIGURATION
# ===========================

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js local
        "https://*.netlify.app",   # Netlify preview/prod
        "https://yourdomain.com"   # Production domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
app.add_exception_handler(Exception, global_exception_handler)

# Structured logging middleware (before routers)
app.add_middleware(LoggingMiddleware)

# API Key middleware (skips when API_KEY is not set)
app.add_middleware(APIKeyMiddleware)

# ===========================
# ROUTER REGISTRATION
# ===========================

# Register all routers; most already define their own prefix.
app.include_router(system_router, tags=["System"])            # router has prefix="/system"
app.include_router(agent_router, tags=["Agents"])            # router has prefix="/agents"
app.include_router(result_router, tags=["Results"])          # router has prefix="/results"
app.include_router(orchestration_router, tags=["Orchestration"])  # routes declare explicit paths
app.include_router(upload_router, tags=["File Uploads"])     # router has prefix="/upload"
app.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])  # mounted at /metrics
app.include_router(dashboard_router, tags=["Dashboard"])     # router has prefix="/dashboard"
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
app.include_router(reports_router, prefix="/reports", tags=["Reports"])

# ===========================
# ROOT ENDPOINT
# ===========================

@app.get("/", tags=["Root"])
def root():
    """Root endpoint with API information."""
    return {
        "name": "ProductForge Backend",
        "version": "2.0.0",
        "status": "running",
        "architecture": "modular_enterprise",
        "uptime_seconds": round(time.time() - BACKEND_START_TIME, 2),
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "endpoints": {
            "system_health": "/system/status",
            "dashboard": "/dashboard",
            "agents": "/agents",
            "orchestration": "/orchestrate",
            "results": "/results"
        }
    }

# ===========================
# LEGACY COMPATIBILITY ROUTES
# ===========================
# These routes maintain backward compatibility with existing frontend

@app.get("/", include_in_schema=False)
def legacy_home():
    """Legacy home endpoint for backward compatibility."""
    return {"status": "running", "agent": "ProductForge Backend"}

# ===========================
# APPLICATION ENTRY POINT
# ===========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main_refactored:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
