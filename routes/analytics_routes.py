"""Analytics routes exposing summary and trends."""
from fastapi import APIRouter
from services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
async def analytics_summary():
    service = AnalyticsService()
    snapshot = service.compute_snapshot()
    return snapshot


@router.get("/trends")
async def analytics_trends():
    service = AnalyticsService()
    return service.trends_24h()
