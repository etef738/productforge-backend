"""
Result and task status routes.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
from models.results_models import EnhancedResult, TaskRequest
from services.result_service import ResultService
from services.task_service import TaskService

router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/ping")
async def ping():
    """Ping endpoint to check if results module is alive."""
    return {"status": "ok", "module": "results"}


@router.post("/task")
async def create_task(task: TaskRequest):
    """Create and queue a new task."""
    service = TaskService()
    return service.queue_task(task)


@router.get("/", response_model=List[EnhancedResult])
async def get_results(limit: int = 10):
    """Get latest results."""
    service = ResultService()
    results = service.list_results(limit=limit)
    
    return results


@router.get("/{job_id}", response_model=EnhancedResult)
async def get_result(job_id: str):
    """Get a specific result by job ID."""
    service = ResultService()
    result = service.get_result(job_id)
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Result for job '{job_id}' not found")
    
    return result

@router.get("/task/{job_id}", response_model=EnhancedResult)
async def get_task_status(job_id: str):
    """Alias route for individual task status (job result)."""
    service = ResultService()
    result = service.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task '{job_id}' not found")
    return result


@router.get("/workflow/{workflow_id}", response_model=List[EnhancedResult])
async def get_workflow_results(workflow_id: str):
    """Get all results for a specific workflow."""
    service = ResultService()
    results = service.get_results_by_workflow(workflow_id)
    
    if not results:
        raise HTTPException(status_code=404, detail=f"No results found for workflow '{workflow_id}'")
    
    return results


@router.get("/agent/{agent_name}", response_model=List[EnhancedResult])
async def get_agent_results(agent_name: str, limit: int = 10):
    """Get all results for a specific agent."""
    service = ResultService()
    results = service.get_results_by_agent(agent_name, limit=limit)
    
    return results

@router.get("/export/json")
async def export_json():
    """Stream JSON export of all recent results."""
    service = ResultService()
    return service.export_json_stream()

@router.get("/export/txt")
async def export_txt():
    """Stream TXT export of all recent results."""
    service = ResultService()
    return service.export_txt_stream()

@router.get("/performance/export")
async def export_performance(format: str = "json"):
    """Export performance metrics (json or csv)."""
    service = ResultService()
    return service.export_performance(fmt=format)
