"""Metrics and observability endpoints.

Provides Prometheus-compatible metrics and deployment verification.
"""
from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
from core.metrics import get_metrics
from services.deploy_check_service import DeployCheckService

router = APIRouter()


@router.get("/", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Export metrics in Prometheus text format.
    
    Returns:
        Plain text metrics in Prometheus exposition format
    """
    metrics = get_metrics()
    return metrics.to_prometheus_format()


@router.get("", response_class=PlainTextResponse)
async def prometheus_metrics_noslash():
    """Support /metrics without trailing slash to avoid redirects."""
    metrics = get_metrics()
    return metrics.to_prometheus_format()


@router.get("/json")
async def json_metrics():
    """Export metrics as JSON for dashboards.
    
    Returns:
        JSON object with current metric values
    """
    metrics = get_metrics()
    return metrics.to_dict()
