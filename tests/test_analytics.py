from fastapi.testclient import TestClient
import main_refactored

client = TestClient(main_refactored.app)


def test_analytics_summary_shape():
    r = client.get('/analytics/summary')
    assert r.status_code == 200
    data = r.json()
    assert 'kpis' in data
    assert 'window' in data
    assert 'totals' in data
    for field in ['total_tasks_processed', 'active_agents_count', 'cache_hit_ratio']:
        assert field in data['kpis']


def test_analytics_trends_shape():
    r = client.get('/analytics/trends')
    assert r.status_code == 200
    data = r.json()
    assert 'series' in data
    assert isinstance(data['series'], list)
    # Expect up to 24 points
    assert len(data['series']) <= 24
