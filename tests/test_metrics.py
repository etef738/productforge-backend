import re
from fastapi.testclient import TestClient
import main_refactored

client = TestClient(main_refactored.app)


def test_metrics_prometheus_format():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Basic Prometheus exposition checks
    assert "productforge_uptime_seconds" in body
    assert "productforge_total_requests" in body
    assert "productforge_redis_latency_ms" in body
    assert "productforge_system_health_cache_hits" in body
    # Ensure numeric value present for uptime
    match = re.search(r"productforge_uptime_seconds (\d+\.\d+)", body)
    assert match, "uptime metric missing numeric value"


def test_metrics_json_endpoint():
    resp = client.get("/metrics/json")
    assert resp.status_code == 200
    data = resp.json()
    for key in ["uptime_seconds", "total_requests", "redis_latency_ms", "system_health_cache_hits"]:
        assert key in data


def test_system_verify_endpoint():
    resp = client.get("/system/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert "checks" in data
    assert "redis" in data["checks"]
    assert "openai" in data["checks"]
    assert "environment" in data["checks"]
    assert "filesystem" in data["checks"]
    assert data["status"] in {"healthy", "degraded", "unhealthy"}