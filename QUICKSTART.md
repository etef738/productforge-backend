# ProductForge Backend - Quick Start Guide

## 🚀 Getting Started in 5 Minutes

### Prerequisites
- Python 3.9+ installed
---

```bash
# Navigate to project directory
cd productforge-backend

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your favorite editor
```

**Required variables**:
```env
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-your-key-here
```

**Optional variables**:
```env
API_KEY=your-secret-key     # Enable API authentication
PORT=8000                    # Server port (default: 8000)
```

---

## Step 3: Start Redis

### macOS (Homebrew)
```bash
brew services start redis
```

### Linux
```bash
## 📊 Analytics & Reporting (Phase 4)

Phase 4 introduces real-time analytics snapshots, 24h trends, and weekly markdown reports.

### Key Endpoints
```bash
# KPI snapshot (cached 60s)
curl -s http://localhost:8000/analytics/summary | jq .

# 24h trend buckets
curl -s http://localhost:8000/analytics/trends | jq .

# Generate a weekly report (markdown file)
curl -s -X POST http://localhost:8000/reports/generate | jq .

# List existing reports
curl -s http://localhost:8000/reports | jq .
```

### Sample /analytics/summary Output (abridged)
```json
{
  "window": {
    "d7": {"tasks": 182},
    "d1": {"tasks": 34},
    "h1": {"tasks": 2}
  },
  "kpis": {
    "active_agents_count": 5,
    "avg_redis_latency_ms": 2.7,
    "cache_hit_ratio": 0.83
  },
  "generated_at": "2025-11-09T16:40:00Z"
}
```

### Weekly Report Filename Pattern
`workspace/reports/report_YYYY-MM-DD.md`

Each generation increments the `productforge_reports_generated_total` counter exposed at `/metrics`.

### Dashboard Enhancements
- Analytics & Trends card (Chart.js line chart + KPIs)
- Generate Report button triggers POST then shows new filename.

### Prometheus Counters Added
| Metric | Purpose |
|--------|---------|
| productforge_reports_generated_total | Reports produced |
| productforge_analytics_snapshots_total | Fresh snapshots (cache misses) |
| productforge_system_health_requests_total | Health endpoint traffic |
| productforge_system_health_cache_hits | Cached health responses served |

### Quick Regression Suite
After adding analytics/reporting features:
```bash
pytest -q
```
Expect majority pass; investigate any failures in legacy tests separately.

---
```

### Docker
```bash
docker run -d -p 6379:6379 redis:alpine
```

### Verify Redis
```bash
redis-cli ping
# Should return: PONG
```

---

## Step 4: Run the Application

### Development Mode (with auto-reload)
```bash
source .venv/bin/activate
uvicorn main_refactored:app --reload --port 8000
```

### Production Mode
```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Background Worker (separate terminal)
```bash
source .venv/bin/activate
python worker.py
```

---

## Step 5: Verify Installation

### Test Health Endpoint
```bash
curl http://localhost:8000/system/health | python3 -m json.tool
```

**Expected response**:
```json
{
  "status": "ok",
  "uptime_seconds": 12.34,
  "uptime_human": "0h 0m 12s",
  "redis_connected": true,
  "active_jobs": 0,
  "total_results": 0,
  "timestamp": "2025-11-09T15:30:00.000000",
  "version": "Enterprise Refactor v2.0"
}
```

### Test Orchestration (if API_KEY set)
```bash
curl -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "job": "Analyze user feedback from latest release",
    "requires_qa": false
  }' | python3 -m json.tool
```

**Expected response**:
```json
{
  "status": "orchestrated",
  "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "steps": [
    {
      "step": "admin_analysis",
      "agent": "general_assistant",
      "job_id": "...",
      "status": "queued"
    },
    {
      "step": "specialist_execution",
      "agent": "analyzer_bot",
      "job_id": "...",
      "status": "queued",
      "depends_on": "..."
    }
  ],
  "estimated_completion": "3-8 minutes",
  "qa_chain_enabled": false
}
```

---

## 🧪 Run Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_system_health.py -v

# Run with coverage
pytest tests/ --cov=services --cov=routes --cov-report=html
```

**Expected output**:
```
============ test session starts ============
tests/test_system_health.py::test_system_ping PASSED
tests/test_system_health.py::test_system_health PASSED
tests/test_orchestration.py::test_orchestrate_endpoint PASSED
...
========== 37 passed, 2 failed in 1.31s ==========
```

*(2 failures are in legacy integrity tests, unrelated to refactor)*

---

## 📊 Access Interactive Docs

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Dashboard**: http://localhost:8000/dashboard

---

## 🔑 API Authentication

### Without API Key (Development)
No `X-API-Key` header required - all endpoints are open.

### With API Key (Production)
Set `API_KEY` in `.env`, then include header in requests:

```bash
# Protected endpoint example
curl -X POST http://localhost:8000/orchestrate \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"job":"Test task","requires_qa":false}'
```

**Public endpoints (no key required)**:
- `/system/health`
- `/system/ping`
- `/dashboard/`
- `/help`

---

## 📝 Common Tasks

### Create a New Agent
```bash
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "name": "custom_agent",
    "role": "specialist",
    "model": "gpt-4",
    "instructions": "You are a specialized agent for...",
    "temperature": 0.7
  }'
```

### List All Workflows
```bash
curl http://localhost:8000/workflows?limit=10
```

### Get Workflow Status
```bash
curl http://localhost:8000/workflows/{workflow_id}
```

### Export Results as JSON
```bash
curl http://localhost:8000/results/export/json > results.json
```

### Upload a ZIP File
```bash
curl -X POST http://localhost:8000/upload/ \
  -H "X-API-Key: your-key" \
  -F "file=@project.zip" \
  -F "project=my_project"
```

### List Recent Uploads
```bash
curl http://localhost:8000/upload/list?limit=20
```

---

## 🔍 Troubleshooting

### Redis Connection Error
```
⚠️ Redis connection warning: Error 111 connecting to localhost:6379
```

**Solution**: Start Redis server
```bash
brew services start redis  # macOS
sudo systemctl start redis # Linux
docker run -p 6379:6379 redis:alpine  # Docker
```

### OpenAI API Key Invalid
```
⚠️ OpenAI API key warning: Invalid API key
```

**Solution**: Check `.env` file has valid key
```bash
grep OPENAI_API_KEY .env
# Should show: OPENAI_API_KEY=sk-...
```

### Port Already in Use
```
ERROR: [Errno 48] Address already in use
```

**Solution**: Use different port or kill existing process
```bash
# Use different port
uvicorn main_refactored:app --port 8001

# OR kill existing process
lsof -ti:8000 | xargs kill -9
```

### Import Errors
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution**: Ensure virtual environment is activated and dependencies installed
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Worker Not Processing Jobs
```bash
# Check worker is running
ps aux | grep worker.py

# Check Redis queue
redis-cli LLEN queue

# Check worker logs
tail -f workspace/logs/worker_log.txt
```

---

## 📈 Performance Tips

### 1. Use Connection Pooling
Redis client already uses pooling - no action needed.

### 2. Enable Result Caching
Health endpoint caches for 5s by default. Adjust if needed:
```python
# routes/system_routes.py
if now - _last_health_ts > 10:  # Change from 5 to 10 seconds
```

### 3. Adjust Upload Limits
```python
# services/upload_service.py
max_size = 100 * 1024 * 1024  # Change from 50MB to 100MB
```

### 4. Monitor Queue Size
```bash
# Check active jobs
redis-cli LLEN queue

# If queue is growing:
# 1. Add more workers
# 2. Scale Redis vertically
# 3. Optimize job processing
```

---

## 🚀 Production Deployment

### Railway
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Deploy
railway up
```

**Set environment variables in Railway dashboard**:
- `REDIS_URL` (use Railway's Redis plugin)
- `OPENAI_API_KEY`
- `API_KEY` (for authentication)
- `RAILWAY_ENVIRONMENT=production`

### Docker
```bash
# Build image
docker build -t productforge-backend .

# Run container
docker run -d \
  -p 8000:8000 \
  -e REDIS_URL=redis://redis:6379 \
  -e OPENAI_API_KEY=sk-... \
  -e API_KEY=your-secret \
  --name productforge-api \
  productforge-backend

# Run worker
docker run -d \
  -e REDIS_URL=redis://redis:6379 \
  -e OPENAI_API_KEY=sk-... \
  --name productforge-worker \
  productforge-backend python worker.py
```

### Heroku
```bash
# Login
heroku login

# Create app
heroku create productforge-api

# Add Redis
heroku addons:create heroku-redis:mini

# Set environment variables
heroku config:set OPENAI_API_KEY=sk-...
heroku config:set API_KEY=your-secret

# Deploy
git push heroku main

# Scale workers
heroku ps:scale worker=1
```

---

## 📚 Next Steps

1. **Read Architecture Docs**: See [ARCHITECTURE.md](./ARCHITECTURE.md)
2. **Review Phase 2 Report**: See [PHASE_2_VERIFICATION_REPORT.md](./PHASE_2_VERIFICATION_REPORT.md)
3. **Explore API Docs**: Visit http://localhost:8000/docs
4. **Customize Agents**: Edit agent configurations in `services/agent_service.py`
5. **Add Templates**: Create custom HTML templates in `workspace/templates/`

---

## 💬 Support

For issues or questions:
1. Check logs: `tail -f workspace/logs/app.log`
2. Review test failures: `pytest tests/ -v`
3. Check Redis connectivity: `redis-cli ping`
4. Verify environment: `cat .env`

---

**Happy coding! 🎉**

---

**Version**: 2.0.0  
**Last Updated**: 2025-11-09

---

## 📊 Monitoring and Metrics

Phase 3 adds first-class observability endpoints.

### Health & Verification
- `GET /system/health` – Cached (5s) snapshot: uptime, Redis, jobs, results.
- `GET /system/status` – Detailed real-time status (OpenAI key, worker heartbeat, log presence).
- `GET /system/verify` – Full startup verification (Redis latency, OpenAI key, env vars, templates, filesystem).

### Metrics Endpoints
- `GET /metrics` – Prometheus exposition format.
- `GET /metrics/json` – JSON struct for dashboards.

### Prometheus Sample Output (truncated)
```
# HELP productforge_uptime_seconds Application uptime in seconds
# TYPE productforge_uptime_seconds gauge
productforge_uptime_seconds 32.15
# HELP productforge_total_requests Total HTTP requests processed
# TYPE productforge_total_requests counter
productforge_total_requests 18
# HELP productforge_redis_latency_ms Last Redis operation latency in milliseconds
# TYPE productforge_redis_latency_ms gauge
productforge_redis_latency_ms 2.91
```

### JSON Metrics Fields
| Field | Description |
|-------|-------------|
| uptime_seconds | Seconds since process start |
| total_requests | Total HTTP requests handled |
| active_workflows | Current active workflow count |
| redis_latency_ms | Last measured Redis latency |
| redis_operations | Total Redis ops recorded |
| system_health_cache_hits | Cache hits for `/system/health` |

### Quick Curl Examples
```bash
curl -s http://localhost:8000/system/verify | jq .
curl -s http://localhost:8000/metrics
curl -s http://localhost:8000/metrics/json | jq .
```

### Adding Prometheus (Optional)
Add a scrape job in your Prometheus config:
```yaml
scrape_configs:
  - job_name: productforge
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

### Alert Ideas (Future)
| Metric | Condition | Action |
|--------|-----------|--------|
| redis_latency_ms | >50ms for 5m | Investigate Redis performance |
| uptime_seconds | Drops to <60 unexpectedly | Restart detection / crash loop |
| total_requests | Flat, expected traffic | Check ingress / networking |

### Troubleshooting Metrics
If `/metrics` is empty:
1. Confirm server started (check logs for `✅ Metrics ready`).
2. Ensure no reverse proxy blocking plain text.
3. Access JSON endpoint for structure debugging.

---
