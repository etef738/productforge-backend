"""
ProductForge Backend - Enterprise Grade FastAPI Application
Modular architecture with clean separation of concerns.
"""
import os
import time
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

# Configuration
from config import settings, validate_environment

# ===========================
# ENVIRONMENT SETUP
# ===========================
load_dotenv()
validate_environment()

# Track backend startup time for health monitoring
BACKEND_START_TIME = time.time()

# ===========================
# APPLICATION INITIALIZATION
# ===========================
app = FastAPI(
    title="ProductForge Backend",
    description="Enterprise-grade multi-agent AI orchestration platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
# STARTUP EVENTS
# ===========================

@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    print("🚀 ProductForge Backend Starting...")
    
    # Validate Redis connection
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        print("✅ Redis connected successfully")
    except Exception as e:
        print(f"⚠️ Redis connection warning: {e}")
    
    # Validate OpenAI API key
    try:
        if validate_openai_key():
            print("✅ OpenAI API key validated")
        else:
            print("⚠️ OpenAI API key not configured")
    except Exception as e:
        print(f"⚠️ OpenAI API key warning: {e}")
    
    print("✅ ProductForge Backend Ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    print("👋 ProductForge Backend Shutting Down...")

# ===========================
# ROUTER REGISTRATION
# ===========================

# Register all routers with their prefixes and tags
app.include_router(
    system_router,
    tags=["System Health"]
)

app.include_router(
    agent_router,
    tags=["Agent Management"]
)

app.include_router(
    orchestration_router,
    tags=["Workflow Orchestration"]
)

app.include_router(
    result_router,
    tags=["Results & Exports"]
)

app.include_router(
    dashboard_router,
    tags=["Dashboard & UI"]
)

app.include_router(
    upload_router,
    tags=["File Uploads"]
)

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
