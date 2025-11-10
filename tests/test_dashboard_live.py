"""Test Phase 8 Live Dashboard functionality."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.metrics import get_metrics


def test_new_metrics():
    """Test that Phase 8 metrics are properly initialized."""
    metrics = get_metrics()
    
    # Test new counters exist
    assert hasattr(metrics, '_dashboard_refresh_total')
    assert hasattr(metrics, '_htmx_events_total')
    assert hasattr(metrics, '_cache_hits_total')
    assert hasattr(metrics, '_cache_misses_total')
    
    # Test increment methods exist
    assert hasattr(metrics, 'increment_dashboard_refresh')
    assert hasattr(metrics, 'increment_htmx_event')
    assert hasattr(metrics, 'increment_cache_hit')
    assert hasattr(metrics, 'increment_cache_miss')
    
    # Test initial values
    assert metrics._dashboard_refresh_total == 0
    assert metrics._htmx_events_total == 0
    assert metrics._cache_hits_total == 0
    assert metrics._cache_misses_total == 0
    
    # Test increment
    metrics.increment_dashboard_refresh()
    assert metrics._dashboard_refresh_total == 1
    
    metrics.increment_htmx_event()
    assert metrics._htmx_events_total == 1
    
    metrics.increment_cache_hit()
    assert metrics._cache_hits_total == 1
    
    metrics.increment_cache_miss()
    assert metrics._cache_misses_total == 1
    
    print("✅ All new metrics tests passed!")


def test_metrics_export():
    """Test that new metrics are included in exports."""
    metrics = get_metrics()
    
    # Test to_dict includes new fields
    data = metrics.to_dict()
    assert 'dashboard_refresh_total' in data
    assert 'htmx_events_total' in data
    assert 'cache_hits_total' in data
    assert 'cache_misses_total' in data
    assert 'cache_hit_rate' in data
    
    # Test cache hit rate calculation
    assert isinstance(data['cache_hit_rate'], float)
    assert 0 <= data['cache_hit_rate'] <= 100
    
    # Test Prometheus format
    prom = metrics.to_prometheus_format()
    assert 'productforge_dashboard_refresh_total' in prom
    assert 'productforge_htmx_events_total' in prom
    assert 'productforge_cache_hits_total' in prom
    assert 'productforge_cache_misses_total' in prom
    
    print("✅ Metrics export tests passed!")


def test_cache_service():
    """Test analytics service caching."""
    from services.analytics_service import AnalyticsService
    
    service = AnalyticsService()
    
    # First call should be cache miss
    snapshot1 = service.compute_snapshot()
    assert 'timestamp' in snapshot1
    assert 'kpis' in snapshot1
    
    # Check that cache was incremented
    metrics = get_metrics()
    initial_misses = metrics._cache_misses_total
    
    # Second call within TTL should be cache hit
    snapshot2 = service.compute_snapshot()
    assert snapshot2 == snapshot1  # Should be identical
    
    hits_after = metrics._cache_hits_total
    assert hits_after > 0, "Cache hit counter should increment"
    
    print("✅ Analytics caching tests passed!")


if __name__ == "__main__":
    print("Running Phase 8 Live Dashboard tests...\n")
    test_new_metrics()
    test_metrics_export()
    # test_cache_service()  # Requires Redis connection
    print("\n🎉 All Phase 8 core tests passed!")
