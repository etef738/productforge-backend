from fastapi.testclient import TestClient
import main_refactored
import os

client = TestClient(main_refactored.app)


def test_generate_report_and_list():
    resp = client.post('/reports/generate')
    assert resp.status_code == 200
    data = resp.json()
    assert 'filename' in data and data['filename'].endswith('.md')
    path = data['report_path']
    assert os.path.exists(path)

    # Now list reports
    resp2 = client.get('/reports')
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert 'reports' in data2
    assert any(r['filename'] == data['filename'] for r in data2['reports'])
