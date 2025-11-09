"""Reports routes for generating and listing reports."""
from fastapi import APIRouter
from services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/generate")
async def generate_report():
    service = ReportService()
    return service.generate_weekly_report()


@router.get("")
async def list_reports():
    service = ReportService()
    return {"reports": service.list_reports()}
